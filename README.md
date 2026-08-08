# DeepGuard AI — AI-Based Deepfake Detection for Cybercrime Prevention

A production-grade, full-stack cybersecurity platform that detects AI-generated /
manipulated content across **images, videos, audio, and text**. It returns
confidence scores, explainable (XAI) verdicts, forensic PDF/CSV reports, and a
learning center for deepfake awareness.

> **Runs out of the box with smart heuristic "dummy" AI predictions**, so the
> entire product works without a trained model. A pluggable interface lets you
> swap in real CNN / ViT / Transformer models later without touching the API or UI.

---

## ✨ Features

- **Landing page** — animated particle background, hero, stats, feature cards, AI workflow
- **Authentication** — register, login, forgot password, JWT, PBKDF2 password hashing, email validation
- **Dashboard** — total scans, fake/real counts, accuracy, recent uploads, quick actions
- **4 Detection modules**
  - Image — Error Level Analysis + CNN/ViT hooks + metadata forensics + heatmap data
  - Video — frame extraction, MediaPipe/Haar face detection, temporal analysis, timeline
  - Audio — Librosa spectrogram, spectral flatness, MFCC variance, voice-clone checks
  - Text — perplexity, burstiness, repetition + suspicious sentence highlighting
- **Results page** — Authentic/Fake badge, confidence meter, risk level, XAI explanation, feature importances, recommendations, PDF/CSV/QR downloads
- **History** — search, filter by type/result, paginate, delete, re-download
- **Analytics** — Chart.js dashboards: daily, weekly, fake-vs-real, by-type, accuracy trend
- **Admin panel** — system stats, user management, logs, model performance, health
- **Learning Center, About, Contact, API Docs** pages
- **Dark/Light mode** with neon-blue cybersecurity theme and glassmorphism
- **Security** — rate limiting, file validation (extension + magic bytes + size), JWT, sanitized inputs, parameterized SQL, XSS-safe rendering
- **Extras** — drag & drop upload, live progress, scan animations, voice assistant (Web Speech API), multi-language UI (EN/ES/HI/FR), QR report, CSV export

---

## 🧱 Tech Stack

| Layer    | Technologies |
|----------|--------------|
| Frontend | React 18, Tailwind CSS 3, Framer Motion, React Router 6, Chart.js, Heroicons, Axios |
| Backend  | Python Flask 3, Flask-JWT-Extended, Flask-SQLAlchemy, Flask-CORS, ReportLab, Pillow, QRCode |
| AI (optional) | OpenCV, MediaPipe, Librosa, HuggingFace Transformers, PyTorch |
| Database | SQLite (default) / MySQL |
| Deploy   | Vercel / Netlify (FE), Render / Railway (BE) |

---

## 📁 Folder Structure

```
deepfake-detection/
├── backend/                      # Flask REST API
│   ├── app.py                    # Application factory + entry point
│   ├── run.py                    # Dev server launcher
│   ├── config.py                 # Environment-driven configuration
│   ├── extensions.py             # Flask extension singletons (db, jwt)
│   ├── models.py                 # Users, ScanHistory, AIPrediction, Report, Log
│   ├── requirements.txt          # Core dependencies
│   ├── requirements-ai.txt       # Optional AI/model dependencies
│   ├── smoke_test.py             # End-to-end API test (34 checks)
│   ├── .env.example              # Environment variables template
│   ├── routes/
│   │   ├── auth.py               # /api/auth/*        (register, login, profile)
│   │   ├── detection.py          # /api/detect/*      (image, video, audio, text)
│   │   ├── history.py            # /api/history/*     (list, stats, delete)
│   │   ├── analytics.py          # /api/analytics/*   (charts data)
│   │   ├── reports.py            # /api/reports/*     (pdf, csv, qr)
│   │   └── admin.py              # /api/admin/*       (users, logs, health)
│   ├── services/
│   │   ├── ai_service.py         # Orchestrator + real-model plug points
│   │   ├── analyze_image.py      # ELA + metadata heuristics
│   │   ├── analyze_video.py      # frame + face + temporal heuristics
│   │   ├── analyze_audio.py      # spectral / MFCC heuristics
│   │   └── analyze_text.py       # perplexity / burstiness heuristics
│   ├── utils/
│   │   ├── security.py           # rate limiter, file validation, sanitizers
│   │   ├── helpers.py            # uploads, timestamps
│   │   └── report_generator.py   # PDF / CSV / QR generation
│   ├── uploads/                  # Uploaded media (auto-created)
│   ├── reports/                  # Generated reports (auto-created)
│   └── models/weights/           # Drop trained weights here for real inference
│
└── frontend/                     # React SPA
    ├── package.json
    ├── tailwind.config.js
    ├── .env.example
    ├── public/index.html
    └── src/
        ├── index.js / App.js / index.css
        ├── api/api.js            # Axios client (JWT interceptor)
        ├── context/              # ThemeContext, AuthContext, LanguageContext
        ├── components/           # Navbar, Footer, ParticleBackground, FileUpload,
        │                         # ResultBadge, ConfidenceBar, ScanLoader, charts, guards…
        ├── pages/                # Home, Login, Register, Dashboard, 4 Detectors,
        │                         # Results, History, Analytics, LearningCenter,
        │                         # About, Contact, Admin, Profile, ApiDocs, NotFound
        └── utils/format.js       # size / date / risk formatters
```

---

## 🚀 Quick Start (Local)

### 1) Backend

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt          # core (heuristic mode works immediately)
# optional, only if you want real model inference:
pip install -r requirements-ai.txt

copy .env.example .env                   # Windows
# cp .env.example .env                   # macOS / Linux

python run.py                            # starts on http://localhost:5000
```

The first run auto-creates the SQLite database and a default admin account
(configured in `.env`, default `admin@deepguard.local` / `Admin@12345`).

### 2) Frontend

```bash
cd frontend
npm install
npm start                                # starts on http://localhost:3000
```

> The frontend proxies `/api` to `http://localhost:5000` during development.
> For production set `REACT_APP_API_URL` (see `.env.example`).

---

## 🔌 API Endpoints (summary)

Base URL: `http://localhost:5000/api` — all protected endpoints require
`Authorization: Bearer <token>`.

| Method | Endpoint                       | Description                          |
|--------|--------------------------------|--------------------------------------|
| POST   | `/auth/register`               | Create account (returns JWT)         |
| POST   | `/auth/login`                  | Login (returns JWT)                  |
| POST   | `/auth/forgot-password`        | Request password reset               |
| POST   | `/auth/reset-password`         | Set new password                     |
| GET    | `/auth/me`                     | Current user profile                 |
| PUT    | `/auth/profile`                | Update profile                       |
| POST   | `/auth/change-password`        | Change password                      |
| POST   | `/detect/image`                | Upload image → verdict               |
| POST   | `/detect/video`                | Upload video → verdict               |
| POST   | `/detect/audio`                | Upload audio → verdict               |
| POST   | `/detect/text`                 | Submit text → verdict                |
| GET    | `/history`                     | List scans (q/type/result/page)      |
| GET    | `/history/stats`               | Dashboard summary                    |
| GET    | `/history/<id>`                | Scan detail (with XAI payload)       |
| DELETE | `/history/<id>`                | Delete scan                          |
| GET    | `/analytics/*`                 | overview, daily, weekly, fake-vs-real, by-type, activity, accuracy-trend |
| GET    | `/reports/<id>/pdf`            | Download PDF report                  |
| GET    | `/reports/<id>/csv`            | Export CSV report                    |
| GET    | `/reports/<id>/qr`             | QR verification image                |
| GET    | `/admin/stats`                 | System stats (admin)                 |
| GET    | `/admin/users`                 | List users (admin)                   |
| DELETE | `/admin/users/<id>`            | Delete user (admin)                  |
| POST   | `/admin/users/<id>/toggle-admin` | Toggle admin role (admin)          |
| GET    | `/admin/logs`                  | Audit logs (admin)                   |
| GET    | `/admin/health`                | System health (admin)                |
| GET    | `/admin/model-performance`     | Model metrics (admin)                |
| GET    | `/docs`                        | Inline API documentation             |

Interactive API docs are also rendered in the app at `/docs`.

---

## 🧠 Integrating a Real Trained Model

The app ships with a deterministic heuristic engine so the full pipeline works
with zero model weights. To use real models:

1. Train / download weights (e.g., FaceForensics++, DFDC, ASVspoof) into
   `backend/models/weights/`.
2. Set `MODEL_ENABLED=true` in `.env`.
3. Implement the `predict_image_real / predict_video_real / predict_audio_real`
   methods in `backend/services/ai_service.py` (`_load_real_models()` is the
   weight-loading hook). Text detection already supports HuggingFace
   `roberta-base-openai-detector` when `MODEL_ENABLED=true`.
4. Restart the backend. The API response schema is unchanged, so the frontend
   needs zero modifications.

### How the heuristic engines work

- **Image**: Error Level Analysis (recompression artifacts), pHash-based
  similarity, color/texture statistics, EXIF forensics.
- **Video**: frame sampling, face detection (MediaPipe → Haar cascade fallback),
  temporal flicker, byte-hash drift.
- **Audio**: spectral flatness, zero-crossing rate, MFCC variance (librosa);
  RIFF header fallback.
- **Text**: n-gram perplexity proxy, sentence-length burstiness, repetition
  ratio; optional HuggingFace RoBERTa detector.

---

## 🗄️ Database Tables

| Table              | Purpose                                   |
|--------------------|-------------------------------------------|
| `users`            | Accounts, hashed passwords, admin flags    |
| `scan_history`     | Every scan: type, file, verdict, confidence, risk, XAI text |
| `ai_predictions`   | Per-scan model metadata + feature importances |
| `reports`          | Generated PDF/CSV/QR references           |
| `logs`             | Audit trail of actions (auth, scans, admin) |

SQLite is used by default (`deepfake.db`). To use MySQL set
`DATABASE_URL=mysql+pymysql://user:pass@host/db` (add `pymysql` to
requirements.txt).

---

## 🔒 Security Model

- **Passwords**: PBKDF2 via `werkzeug.security` — never stored in plain text.
- **Auth**: short-lived JWT access tokens (no cookies ⇒ no CSRF surface).
- **SQL Injection**: all queries are parameterized through SQLAlchemy.
- **XSS**: API returns data only; React escapes all dynamic output.
- **Uploads**: extension whitelist + magic-byte sniffing + size cap; files are
  random-renamed to prevent path traversal.
- **Rate limiting**: in-memory sliding window per user/IP on auth + detect routes.
- **Input sanitization**: control characters stripped, length caps enforced.

---

## ☁️ Deployment

### Frontend → Vercel / Netlify

```bash
cd frontend
npm run build        # outputs build/
```

- **Vercel**: import repo → framework `Create React App` → build `npm run build`, output `build`. Set env `REACT_APP_API_URL=https://<backend>.onrender.com/api`.
- **Netlify**: build command `npm run build`, publish directory `build`, env var as above.

### Backend → Render / Railway

```bash
cd backend
pip install -r requirements.txt
gunicorn -w 4 -b 0.0.0.0:$PORT app:app
```

Set env vars: `SECRET_KEY`, `JWT_SECRET_KEY`, `DATABASE_URL`,
`CORS_ORIGINS=https://<frontend>.vercel.app`, `MODEL_ENABLED=false`.

### Database & AI model hosting

- Database: use a managed MySQL (Render/Railway) or SQLite on a persistent disk.
- AI model hosting: run inference on a GPU instance (or keep `MODEL_ENABLED=false`
  for the heuristic engine which is CPU-only).

---

## 🧪 Testing

Backend end-to-end smoke test (boots the app and exercises auth, all 4 detectors,
history, analytics, reports, admin):

```bash
cd backend
python smoke_test.py        # expects 34 PASS, 0 FAIL
```

Frontend:

```bash
cd frontend
npm test
npm run build               # verifies a clean production compile
```

---

## 📄 Documentation Files

- `README.md` — this file
- `backend/.env.example` — backend environment template
- `frontend/.env.example` — frontend environment template
- `/docs` route in the app — interactive API documentation
- `backend/smoke_test.py` — testing guide / reference

---

## 📝 License

Educational project — use at your own risk. Deepfake detection is probabilistic;
treat verdicts as forensic guidance, not legal proof.
