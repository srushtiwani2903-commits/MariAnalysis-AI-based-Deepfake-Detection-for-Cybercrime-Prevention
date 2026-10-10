"""One-time history merge: import scan history from another MariAnalysis /
DeepGuard SQLite database into this app's database.

Use this when several machines ran the app separately (each with its own
``deepfake.db``) and you now want every past scan to show up in a single,
shared history - alongside the live (real-time) scans that already land in
one central DB once all laptops point at the same backend.

What it does
------------
* Reads the *source* DB with plain sqlite3 (so old schemas are fine).
* Remaps users: matches by email, then username, else creates a new user
  (copying the original password hash, so logins keep working).
* Imports ``scan_history`` + ``ai_predictions`` (+ ``reports``,
  ``evidence_cases``, ``blockchain_blocks`` when present in the source).
* Skips rows that already exist (matched by file hash, then by
  user/type/filename/timestamp), so it is safe to re-run.
* Copies uploaded media, PDF/CSV reports and heatmaps into this project and
  rewrites the stored paths to the central folders.

Usage
-----
    cd backend
    .venv\\Scripts\\activate
    python merge_history.py --source "C:\\path\\to\\other\\backend\\deepfake.db"
    python merge_history.py --source ... --dry-run     # preview only

Stop the backend first (so SQLite is not locked), merge, then start it again.
"""
import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime

from app import create_app
from config import Config
from extensions import db
from models import (AIPrediction, BlockchainBlock, EvidenceCase, Report,
                    ScanHistory, User)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _parse_dt(value):
    """Parse the many datetime string shapes SQLite may hold -> naive datetime."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    text = str(value).strip().replace("Z", "").replace("+00:00", "")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text).replace(tzinfo=None)
    except ValueError:
        return None


def _loads(value, default):
    if value is None or value == "":
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return default


def _sha256(path, chunk=1 << 20):
    if not path or not os.path.isfile(path):
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _table_exists(cur, name):
    return cur.execute(
        "select 1 from sqlite_master where type='table' and name=?",
        (name,)).fetchone() is not None


def _unique_username(base):
    base = (base or "merged_user").strip() or "merged_user"
    name, n = base, 1
    while User.query.filter(db.func.lower(User.username) == name.lower()).first():
        n += 1
        name = f"{base}_m{n}"
    return name


def _unique_email(base):
    base = (base or "").strip().lower()
    if not base:
        base = "merged@local"
    local, _, domain = base.partition("@")
    if not domain:
        domain = "local"
    email, n = base, 1
    while User.query.filter(db.func.lower(User.email) == email).first():
        n += 1
        email = f"{local}+m{n}@{domain}"
    return email


def _copy_into(src_path, dest_dir):
    """Copy src_path into dest_dir (same basename); return new path or None."""
    if not src_path or not os.path.isfile(src_path):
        return None
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, os.path.basename(src_path))
    if os.path.abspath(src_path) != os.path.abspath(dest):
        shutil.copy2(src_path, dest)
    return dest


# --------------------------------------------------------------------------- #
# merge
# --------------------------------------------------------------------------- #
def merge(source_db, dry_run=False, uploads_dir=None, reports_dir=None,
          heatmaps_dir=None):
    src_dir = os.path.dirname(os.path.abspath(source_db))
    uploads_dir = uploads_dir or os.path.join(src_dir, "uploads")
    reports_dir = reports_dir or os.path.join(src_dir, "reports")
    heatmaps_dir = heatmaps_dir or os.path.join(reports_dir, "heatmaps")

    src = sqlite3.connect(source_db)
    src.row_factory = sqlite3.Row
    cur = src.cursor()

    user_map = {}      # source user id -> target User
    scan_map = {}      # source scan id -> target scan id
    stats = {"users_created": 0, "users_matched": 0, "scans": 0,
             "scans_skipped": 0, "predictions": 0, "reports": 0,
             "cases": 0, "blocks": 0, "files_copied": 0}

    def resolve_user(src_uid):
        if src_uid in user_map:
            return user_map[src_uid]
        row = src.execute("select * from users where id=?", (src_uid,)).fetchone()
        if row is None:
            return None
        email = (row["email"] or "").strip()
        username = (row["username"] or "").strip()
        user = None
        if email:
            user = User.query.filter(
                db.func.lower(User.email) == email.lower()).first()
        if user is None and username:
            user = User.query.filter(
                db.func.lower(User.username) == username.lower()).first()
            if user is not None:
                print(f"  [user] matched by username '{username}' "
                      f"(source email {email or 'none'})")
        if user is None:
            user = User(
                username=_unique_username(username),
                email=_unique_email(email),
                password_hash=row["password_hash"] or "!merged",
                full_name=(row["full_name"] if "full_name" in row.keys() else "") or "",
                is_admin=bool(row["is_admin"]) if "is_admin" in row.keys() else False,
                is_verified=bool(row["is_verified"]) if "is_verified" in row.keys() else False,
                created_at=_parse_dt(row["created_at"]),
                last_login=_parse_dt(row["last_login"]) if "last_login" in row.keys() else None,
            )
            db.session.add(user)
            db.session.flush()
            stats["users_created"] += 1
            print(f"  [user] created '{user.username}' <{user.email}>")
        else:
            stats["users_matched"] += 1
        user_map[src_uid] = user
        return user

    def resolve_scan(src_scan_id):
        """Map a source scan id to its new id, importing if needed."""
        if src_scan_id in scan_map:
            return scan_map[src_scan_id]
        row = src.execute("select * from scan_history where id=?",
                          (src_scan_id,)).fetchone()
        if row is None:
            return None
        new_id = import_scan(row)
        return new_id

    def import_scan(row):
        if row["id"] in scan_map:
            return scan_map[row["id"]]
        keys = row.keys()
        user = resolve_user(row["user_id"])
        if user is None:
            stats["scans_skipped"] += 1
            return None

        # timestamp + hash
        created = _parse_dt(row["created_at"])
        src_file = row["file_path"] if "file_path" in keys else ""
        file_hash = _sha256(src_file)

        # dedupe: the stored random filename is unique per scan, so it is the
        # reliable identity. (File *content* hash must NOT be used - the same
        # image/video can legitimately be scanned more than once.)
        existing = None
        if row["filename"]:
            existing = ScanHistory.query.filter_by(
                user_id=user.id, filename=row["filename"]).first()
        if existing is None:
            existing = ScanHistory.query.filter_by(
                user_id=user.id,
                scan_type=row["scan_type"],
                original_filename=(row["original_filename"] or ""),
                created_at=created,
                file_size=(row["file_size"] or 0),
            ).first()
        if existing is not None:
            stats["scans_skipped"] += 1
            print(f"  [scan#{row['id']}] skipped (already present as #{existing.id})")
            return existing.id

        # copy the media file (if still on disk) and repoint to central folder
        new_file_path = src_file
        if not dry_run:
            copied = _copy_into(src_file, Config.UPLOAD_FOLDER)
            if copied:
                new_file_path = copied
                stats["files_copied"] += 1

        metadata = _loads(row["scan_metadata"] if "scan_metadata" in keys else None, {})
        # heatmap file, if any, copied alongside the report assets
        heat = metadata.get("heatmap_file") if isinstance(metadata, dict) else None
        if heat and not dry_run:
            copied = _copy_into(os.path.join(heatmaps_dir, os.path.basename(heat)),
                                Config.HEATMAP_FOLDER)
            if copied:
                stats["files_copied"] += 1

        scan = ScanHistory(
            user_id=user.id,
            scan_type=row["scan_type"],
            filename=row["filename"],
            original_filename=row["original_filename"] or "",
            file_path=new_file_path,
            file_size=row["file_size"] or 0,
            result=row["result"],
            confidence=row["confidence"] or 0.0,
            fake_probability=row["fake_probability"] or 0.0,
            risk_level=row["risk_level"] or "low",
            explanation=row["explanation"] or "",
            recommendations=row["recommendations"] or "",
            suspicious_sections=_loads(row["suspicious_sections"], []),
            trust_score=row["trust_score"] if "trust_score" in keys else 0.0,
            file_hash=file_hash,
            models=_loads(row["models"], []) if "models" in keys else [],
            reasons=_loads(row["reasons"], []) if "reasons" in keys else [],
            processing_time_ms=row["processing_time_ms"] or 0,
            scan_metadata=metadata if isinstance(metadata, dict) else {},
            created_at=created,
        )
        if dry_run:
            db.session.rollback()
            scan_map[row["id"]] = -1
            stats["scans"] += 1
            print(f"  [scan#{row['id']}] would import ({row['scan_type']} "
                  f"{row['result']}, owner {user.username})")
            return -1
        db.session.add(scan)
        db.session.flush()
        scan_map[row["id"]] = scan.id
        stats["scans"] += 1
        print(f"  [scan#{row['id']}] -> #{scan.id} ({row['scan_type']} "
              f"{row['result']}, owner {user.username})")
        return scan.id

    print(f"Source : {source_db}")
    print(f"Target : {db.engine.url}")
    print("Importing scans...")
    for row in src.execute("select * from scan_history order by id").fetchall():
        import_scan(row)

    # ---- predictions ----
    if _table_exists(cur, "ai_predictions"):
        for p in src.execute("select * from ai_predictions order by id").fetchall():
            new_scan = resolve_scan(p["scan_id"]) if p["scan_id"] is not None else None
            if dry_run or new_scan in (None, -1):
                continue
            if AIPrediction.query.filter_by(scan_id=new_scan).first():
                continue
            db.session.add(AIPrediction(
                scan_id=new_scan,
                model_name=p["model_name"] or "heuristic-ensemble-v1",
                model_version=p["model_version"] or "1.0.0",
                prediction=p["prediction"],
                confidence=p["confidence"],
                features=_loads(p["features"], {}) if "features" in p.keys() else {},
                created_at=_parse_dt(p["created_at"]) if "created_at" in p.keys() else None,
            ))
            stats["predictions"] += 1

    # ---- reports ----
    if _table_exists(cur, "reports"):
        for r in src.execute("select * from reports order by id").fetchall():
            new_scan = resolve_scan(r["scan_id"])
            if dry_run or new_scan in (None, -1):
                continue
            scan = db.session.get(ScanHistory, new_scan)
            if scan is None or Report.query.filter_by(scan_id=new_scan).first():
                continue
            new_path = r["file_path"]
            copied = _copy_into(r["file_path"], Config.REPORT_FOLDER)
            if copied:
                new_path = copied
                stats["files_copied"] += 1
            db.session.add(Report(
                scan_id=new_scan, user_id=scan.user_id,
                format=r["format"] or "pdf", file_path=new_path,
                created_at=_parse_dt(r["created_at"]) if "created_at" in r.keys() else None,
            ))
            stats["reports"] += 1

    # ---- evidence cases ----
    if _table_exists(cur, "evidence_cases"):
        for c in src.execute("select * from evidence_cases order by id").fetchall():
            new_scan = resolve_scan(c["scan_id"])
            if dry_run or new_scan in (None, -1):
                continue
            if EvidenceCase.query.filter_by(scan_id=new_scan).first():
                continue
            if EvidenceCase.query.filter_by(case_id=c["case_id"]).first():
                continue
            user = resolve_user(c["user_id"])
            db.session.add(EvidenceCase(
                case_id=c["case_id"], scan_id=new_scan,
                user_id=user.id if user else None,
                status=c["status"] or "open", platform=c["platform"] or "",
                notes=c["notes"] or "", report_hash=c["report_hash"] or "",
                created_at=_parse_dt(c["created_at"]) if "created_at" in c.keys() else None,
            ))
            stats["cases"] += 1

    # ---- blockchain ledger ----
    if _table_exists(cur, "blockchain_blocks"):
        for b in src.execute("select * from blockchain_blocks order by \"index\"").fetchall():
            new_scan = resolve_scan(b["scan_id"]) if b["scan_id"] is not None else None
            if dry_run or new_scan in (None, -1):
                continue
            if BlockchainBlock.query.filter_by(scan_id=new_scan).first():
                continue
            max_index = db.session.query(db.func.max(BlockchainBlock.index)).scalar() or 0
            db.session.add(BlockchainBlock(
                index=max_index + 1, scan_id=new_scan,
                case_id=b["case_id"], file_hash=b["file_hash"] or "",
                report_hash=b["report_hash"] or "",
                timestamp=b["timestamp"], data=_loads(b["data"], {}),
                prev_hash=b["prev_hash"], nonce=b["nonce"] or 0, hash=b["hash"],
            ))
            stats["blocks"] += 1

    if dry_run:
        db.session.rollback()
        print("\n[dry-run] no changes written.")
    else:
        db.session.commit()

    src.close()
    print("\n=== summary ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    return stats


def main():
    ap = argparse.ArgumentParser(description="Merge another DB's history into this app.")
    ap.add_argument("--source", required=True, help="path to the other deepfake.db")
    ap.add_argument("--dry-run", action="store_true", help="preview without writing")
    ap.add_argument("--uploads", help="source uploads folder (default <source_dir>/uploads)")
    ap.add_argument("--reports", help="source reports folder (default <source_dir>/reports)")
    ap.add_argument("--heatmaps", help="source heatmaps folder (default <reports>/heatmaps)")
    args = ap.parse_args()

    if not os.path.isfile(args.source):
        print(f"ERROR: source DB not found: {args.source}", file=sys.stderr)
        sys.exit(1)

    app = create_app()
    with app.app_context():
        merge(args.source, dry_run=args.dry_run, uploads_dir=args.uploads,
              reports_dir=args.reports, heatmaps_dir=args.heatmaps)


if __name__ == "__main__":
    main()
