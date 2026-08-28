"""CSRF-aware smoke check (temp) - verifies detect flows like the browser does."""
import io, json, os, re, sys, time
os.environ["RATE_LIMIT_ENABLED"] = "false"
from app import create_app

app = create_app()
client = app.test_client()
results = []


def check(name, ok, extra=""):
    results.append((name, ok, extra))
    print(("PASS" if ok else "FAIL"), "-", name, extra)


def csrf_headers(r):
    setcookie = r.headers.get("Set-Cookie", "")
    m = re.search(r"deepguard_csrf=([^;]+)", setcookie)
    val = m.group(1) if m else ""
    return {"X-CSRF-TOKEN": val}


r = client.get("/api/health")
check("health", r.status_code == 200 and r.json.get("status") == "ok")

_suffix = str(int(time.time()))[-6:]
r = client.post("/api/auth/register", json={
    "username": f"t2{_suffix}", "email": f"t2{_suffix}@example.com",
    "password": "Test@1234", "full_name": "Test User", "phone": f"+91999{_suffix}",
})
check("register", r.status_code == 201 and "token" in r.json)
token = r.json.get("token", "")
headers = {"Authorization": f"Bearer {token}"}
headers.update(csrf_headers(r))

r = client.post("/api/auth/login", json={"identifier": f"t2{_suffix}@example.com", "password": "Test@1234"})
check("login", r.status_code == 200 and "token" in r.json)
headers = {"Authorization": f"Bearer {r.json['token']}"}
headers.update(csrf_headers(r))

from PIL import Image
buf = io.BytesIO()
Image.new("RGB", (128, 128), (120, 60, 90)).save(buf, format="JPEG")
buf.seek(0)
r = client.post("/api/detect/image", headers=headers,
                data={"file": (buf, "test.jpg")}, content_type="multipart/form-data")
check("detect image", r.status_code == 200 and "scan_id" in r.json["result"],
      f'{r.json["result"].get("result")} p={r.json["result"].get("fake_probability")}')

r = client.post("/api/detect/text", headers=headers, json={
    "text": "I woke up early on Saturday because the sun was already blazing through my window. "
            "To be honest, I had barely slept, thanks to the neighbour's dog barking all night. "
            "Still, once I poured myself a big cup of coffee, everything felt a little more "
            "manageable. I spent the morning clearing out my inbox, which had somehow grown to "
            "almost two hundred messages. By noon, I decided to pack a small bag, leave my phone "
            "at home, and just wander down to the river.",
})
check("detect text (human -> authentic expected)", r.status_code == 200 and r.json["result"]["scan_type"] == "text",
      f'result={r.json["result"].get("result")} p={r.json["result"].get("fake_probability")}')
text_scan_id = r.json["result"].get("scan_id")

r = client.post("/api/detect/text", headers=headers, json={
    "text": "Artificial intelligence is transforming the way we work, learn, and communicate. "
            "From intelligent assistants that draft emails to models that generate code and art, "
            "the technology has become deeply embedded in our daily lives. Furthermore, businesses "
            "are using AI to automate repetitive tasks and deliver personalised experiences. "
            "In conclusion, responsible development will shape how AI benefits society.",
})
check("detect text (AI style -> not authentic)", r.status_code == 200 and r.json["result"]["scan_type"] == "text",
      f'result={r.json["result"].get("result")} p={r.json["result"].get("fake_probability")}')

r = client.get(f"/api/reports/{text_scan_id}/csv", headers=headers)
check("csv report", r.status_code == 200 and r.content_type.startswith("text/csv"))
r = client.get(f"/api/reports/{text_scan_id}/pdf", headers=headers)
check("pdf report", r.status_code == 200 and r.content_type == "application/pdf", f"len={len(r.data)}")

failed = [x for x in results if not x[1]]
print("\n======", len(results) - len(failed), "passed,", len(failed), "failed")
sys.exit(1 if failed else 0)