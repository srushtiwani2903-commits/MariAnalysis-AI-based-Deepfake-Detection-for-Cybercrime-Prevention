"""Quick smoke test: boots the app and exercises the core API flow."""
import io
import json
import os
import sys

os.environ["RATE_LIMIT_ENABLED"] = "false"

from app import create_app  # noqa: E402

app = create_app()
client = app.test_client()

results = []


def check(name, ok, extra=""):
    results.append((name, ok, extra))
    print(("PASS" if ok else "FAIL"), "-", name, extra)


# 1. Health
r = client.get("/api/health")
check("health", r.status_code == 200 and r.json.get("status") == "ok")

# 2. Register
r = client.post("/api/auth/register", json={
    "username": "tester", "email": "tester@example.com",
    "password": "Test@1234", "full_name": "Test User",
})
check("register", r.status_code == 201, r.json.get("message", ""))
token = r.json.get("token", "")
headers = {"Authorization": f"Bearer {token}"}

# 3. Duplicate register rejected
r = client.post("/api/auth/register", json={
    "username": "tester", "email": "tester@example.com", "password": "Test@1234",
})
check("register duplicate", r.status_code == 409)

# 4. Login
r = client.post("/api/auth/login", json={"identifier": "tester@example.com", "password": "Test@1234"})
check("login", r.status_code == 200 and "token" in r.json)

# 5. Bad login
r = client.post("/api/auth/login", json={"identifier": "tester@example.com", "password": "wrong"})
check("login bad password", r.status_code == 401)

# 6. Me
r = client.get("/api/auth/me", headers=headers)
check("me", r.status_code == 200 and r.json["user"]["username"] == "tester")

# 7. Weak password rejected
r = client.post("/api/auth/register", json={
    "username": "x", "email": "x@y.com", "password": "short",
})
check("weak password rejected", r.status_code == 400)

# 8. Image detection
from PIL import Image
buf = io.BytesIO()
Image.new("RGB", (128, 128), (120, 60, 90)).save(buf, format="JPEG")
buf.seek(0)
r = client.post("/api/detect/image", headers=headers,
                data={"file": (buf, "test.jpg")}, content_type="multipart/form-data")
check("detect image", r.status_code == 200 and "scan_id" in r.json["result"],
      json.dumps({k: r.json["result"].get(k) for k in ("result", "confidence", "fake_probability", "risk_level")}))
image_scan_id = r.json["result"].get("scan_id")

# 9. Video detection (fake small mp4-ish file - heuristic path still works)
buf = io.BytesIO(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 4096)
buf.seek(0)
r = client.post("/api/detect/video", headers=headers,
                data={"file": (buf, "test.mp4")}, content_type="multipart/form-data")
check("detect video", r.status_code == 200, r.json.get("result", {}).get("result", "?"))

# 10. Audio detection
buf = io.BytesIO(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00" + b"\x00" * 256)
buf.seek(0)
r = client.post("/api/detect/audio", headers=headers,
                data={"file": (buf, "test.wav")}, content_type="multipart/form-data")
check("detect audio", r.status_code == 200, r.json.get("result", {}).get("result", "?"))

# 11. Text detection
r = client.post("/api/detect/text", headers=headers, json={
    "text": "The quick brown fox jumps over the lazy dog. Technology continues to evolve at a rapid pace. "
            "Artificial intelligence transforms every industry across the globe. Innovation drives progress "
            "forward every single day. Companies adopt new tools to remain competitive in the modern era.",
})
check("detect text", r.status_code == 200 and r.json["result"]["scan_type"] == "text",
      f"result={r.json['result'].get('result')} conf={r.json['result'].get('confidence')}")
text_scan_id = r.json["result"].get("scan_id")

# 12. History list + stats
r = client.get("/api/history", headers=headers)
check("history list", r.status_code == 200 and r.json["total"] >= 3, f"total={r.json['total']}")
r = client.get("/api/history/stats", headers=headers)
check("history stats", r.status_code == 200 and r.json["total_scans"] >= 3)

# 13. History filter/search
r = client.get("/api/history?type=image&q=test", headers=headers)
check("history filter", r.status_code == 200 and r.json["total"] >= 1)

# 14. Analytics
for path in ("/api/analytics/overview", "/api/analytics/daily?days=7", "/api/analytics/fake-vs-real",
             "/api/analytics/by-type", "/api/analytics/activity", "/api/analytics/accuracy-trend"):
    r = client.get(path, headers=headers)
    check(f"analytics {path}", r.status_code == 200)

# 15. Reports
r = client.get(f"/api/reports/{image_scan_id}/pdf", headers=headers)
check("pdf report", r.status_code == 200 and r.content_type == "application/pdf", f"len={len(r.data)}")
r = client.get(f"/api/reports/{text_scan_id}/csv", headers=headers)
check("csv report", r.status_code == 200 and r.content_type.startswith("text/csv"))
r = client.get(f"/api/reports/{image_scan_id}/qr", headers=headers)
check("qr report", r.status_code == 200)

# 16. Detail + delete
r = client.get(f"/api/history/{text_scan_id}", headers=headers)
check("history detail", r.status_code == 200 and "explanation" in r.json["scan"])
r = client.delete(f"/api/history/{text_scan_id}", headers=headers)
check("history delete", r.status_code == 200)
r = client.get(f"/api/history/{text_scan_id}", headers=headers)
check("history deleted 404", r.status_code == 404)

# 17. Auth required
r = client.get("/api/history")
check("auth required", r.status_code == 401)

# 18. Admin endpoints (admin seeded from env default)
r = client.post("/api/auth/login", json={"identifier": "admin@deepguard.local", "password": "Admin@12345"})
admin_headers = {"Authorization": f"Bearer {r.json['token']}"} if r.status_code == 200 else {}
check("admin login", r.status_code == 200)
for path in ("/api/admin/stats", "/api/admin/users", "/api/admin/logs",
             "/api/admin/health", "/api/admin/model-performance"):
    rr = client.get(path, headers=admin_headers)
    check(f"admin {path}", rr.status_code == 200)

# 19. Non-admin blocked from admin
r = client.get("/api/admin/stats", headers=headers)
check("non-admin blocked", r.status_code == 403)

failed = [x for x in results if not x[1]]
print("\n======", len(results) - len(failed), "passed,", len(failed), "failed")
sys.exit(1 if failed else 0)
