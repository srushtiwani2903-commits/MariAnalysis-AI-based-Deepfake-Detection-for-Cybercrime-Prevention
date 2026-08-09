"""Simulated blockchain evidence ledger.

Each scan (optionally linked to an EvidenceCase) goes into a chained block:
hash = SHA-256(index | timestamp | prev_hash | nonce | data). Tampering with
any stored hash or link breaks verification, so the evidence is tamper-evident.

It's a demonstration of the concept (SHA-256 + simulated proof-of-work), not a
real distributed network.
"""
import hashlib
from datetime import datetime, timezone

from extensions import db
from models import BlockchainBlock

GENESIS_PREV = "0" * 64
DIFFICULTY = 3  # leading zeros required in each block hash


def sha256_file(path):
    """Streaming SHA-256 of a file. Returns hex digest (or '' if unreadable)."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _candidate_hash(index, timestamp, prev_hash, nonce, data):
    payload = f"{index}|{timestamp}|{prev_hash}|{nonce}|{data}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _proof_of_work(index, timestamp, prev_hash, data, difficulty=DIFFICULTY):
    prefix = "0" * difficulty
    nonce = 0
    while True:
        guess = _candidate_hash(index, timestamp, prev_hash, nonce, data)
        if guess.startswith(prefix):
            return nonce
        nonce += 1


def last_block():
    return BlockchainBlock.query.order_by(BlockchainBlock.index.desc()).first()


def _ensure_genesis():
    if last_block() is None:
        ts = datetime.now(timezone.utc).isoformat()
        genesis = BlockchainBlock(
            index=0,
            timestamp=ts,
            data={"type": "genesis", "app": "MariAnalysis Evidence Ledger"},
            prev_hash=GENESIS_PREV,
            nonce=0,
        )
        genesis.hash = _candidate_hash(0, ts, GENESIS_PREV, 0, genesis.data)
        db.session.add(genesis)
        db.session.commit()
    return last_block()


def add_block(scan=None, file_hash="", report_hash="", case_id="", extra=None):
    """Append a new block anchoring the given scan/evidence. Returns the block dict."""
    _ensure_genesis()
    prev = last_block()
    ts = datetime.now(timezone.utc).isoformat()
    data = {
        "scan_id": scan.id if scan else None,
        "case_id": case_id,
        "file_hash": file_hash or (scan.file_hash if scan else ""),
        "report_hash": report_hash,
        "result": scan.result if scan else "",
        "fake_probability": round(scan.fake_probability, 2) if scan else 0,
        "trust_score": round(scan.trust_score, 2) if scan else 0,
    }
    if extra:
        data.update(extra)
    block = BlockchainBlock(
        index=prev.index + 1,
        scan_id=scan.id if scan else None,
        case_id=case_id or None,
        file_hash=data["file_hash"],
        report_hash=report_hash,
        timestamp=ts,
        data=data,
        prev_hash=prev.hash,
        nonce=0,
    )
    block.nonce = _proof_of_work(block.index, ts, prev.hash, data)
    block.hash = _candidate_hash(block.index, ts, prev.hash, block.nonce, data)
    db.session.add(block)
    db.session.commit()
    return block.to_dict()


def is_chain_valid():
    """Recompute every block hash and verify linkage + proof-of-work."""
    blocks = BlockchainBlock.query.order_by(BlockchainBlock.index.asc()).all()
    if not blocks:
        return True, []
    if blocks[0].prev_hash != GENESIS_PREV:
        return False, ["Genesis block is not anchored correctly."]
    problems = []
    for i in range(1, len(blocks)):
        b = blocks[i]
        p = blocks[i - 1]
        if b.prev_hash != p.hash:
            problems.append(f"Block {b.index}: previous hash mismatch (chain broken).")
            continue
        recomputed = _candidate_hash(b.index, b.timestamp, b.prev_hash, b.nonce, b.data)
        if recomputed != b.hash:
            problems.append(f"Block {b.index}: hash was tampered with.")
        elif not recomputed.startswith("0" * DIFFICULTY):
            problems.append(f"Block {b.index}: proof-of-work invalid.")
    return len(problems) == 0, problems


def verify_scan(scan_id):
    """Return the block for a scan plus chain-integrity status."""
    block = BlockchainBlock.query.filter_by(scan_id=scan_id).first()
    if not block:
        return None
    recomputed = _candidate_hash(block.index, block.timestamp, block.prev_hash,
                                 block.nonce, block.data)
    prev_ok = True
    if block.index > 0:
        prev = BlockchainBlock.query.filter_by(index=block.index - 1).first()
        prev_ok = bool(prev and prev.hash == block.prev_hash)
    return {
        "block": block.to_dict(),
        "intact": recomputed == block.hash and prev_ok,
        "chain_valid": is_chain_valid()[0],
    }


def chain_summary(limit=25):
    blocks = (BlockchainBlock.query.order_by(BlockchainBlock.index.desc())
              .limit(limit).all())
    return [b.to_dict() for b in blocks]
