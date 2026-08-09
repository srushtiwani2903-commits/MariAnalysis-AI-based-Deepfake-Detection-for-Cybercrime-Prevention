# MariAnalysis — AI-Based Deepfake Detection for Cybercrime Prevention

A production-grade, full-stack cybersecurity platform that detects AI-generated /
manipulated content across **images, videos, audio, and text**. It returns
confidence scores, explainable (XAI) verdicts, forensic PDF/CSV reports, and a
learning center for deepfake awareness.

> **Runs out of the box with smart heuristic AI predictions** (no model weights).
> Deepfake analysis runs on deterministic, explainable heuristic engines for
> images, video, audio and text. Model *training* code has been removed; the
> Kaggle subsystem exists purely as an on-demand dataset fetch/extract/use
> pipeline and never persists data in the project.

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
- **URL scanning** — paste a link to a media file and the backend fetches + analyzes it
  (`POST /api/detect/url`), no manual download needed
- **Automated Kaggle data pipeline** — deepfake datasets are fetched **directly from
  Kaggle on-demand**, extracted to a temp cache, used, then the temp cache is
  auto-deleted. Nothing is stored in the project. No model training is performed.
- **Results page** — Authentic/Fake badge, confidence meter, risk level, XAI explanation, feature importances, recommendations, PDF/CSV/QR downloads
- **Multi-model ensemble** — per-model verdict table (CNN / Transformer / CLIP / Audio / N-gram) plus a 0-100 evidence trust score on every result
- **Explainable AI checklist** — pass/fail detection reasons (metadata, ELA, compression, noise, face consistency, network age…) shown on results and in the PDF
- **Manipulation heatmap** — red-region visualisation of AI-altered areas for images (`GET /api/reports/<id>/heatmap`)
- **Blockchain evidence ledger** — report a detected deepfake as a cybercrime case (ID like `DF-2026-0001`), anchoring file hash + report hash into a chained SHA-256 ledger; verify integrity any time (`/api/evidence/*`)
- **Live webcam detection** — `/detect/realtime` streams frames for a live fake-confidence gauge (frames never persisted)
- **Email & phishing scanner** — `/detect/email` scores urgency, links, sender-reply mismatch and AI-written wording
- **Social post detection** — `/detect/social` analyses an image and its caption together (image + text pipeline)
- **AI assistant chatbot** — `/api/chat` knowledge base (deepfakes, scams, cyber laws, tool guidance) + floating chat widget
- **Organisation dashboard** — `/api/analytics/org-dashboard` risk distribution, threat sources, flagged-rate + CSV export (`/api/analytics/org/export`); admins see global stats
- **Deepfake-type leaderboard** — `/api/analytics/deepfake-types` blends user scan mix with public baseline distribution
- **Browser extension prototype** — `/extension` Manifest V3 extension: right-click any image to check it, inline badges, popup (uses per-user API keys from `/api/keys`)
- **API keys** — `/api/keys` create/revoke keys (SHA-256 hashed, shown once) for the browser extension / external tooling
- **History** — search, filter by type/result, paginate, delete, re-download
- **Analytics** — Chart.js dashboards: daily, weekly, fake-vs-real, by-type, accuracy trend
- **Admin panel** — system stats, user management, logs, model performance, health
- **Learning Center, About, Contact, API Docs** pages
- **Dark/Light mode** with neon-blue cybersecurity theme and glassmorphism
- **Security** — rate limiting, **IDPS (fail2ban-style IP lockout + intrusion/audit logs)**, file validation (extension + magic bytes + size), JWT, PBKDF2 password hashing, sanitized inputs, parameterized SQL, XSS-safe rendering, security headers (CSP, X-Frame-Options, nosniff)
- **Extras** — drag & drop upload, live progress, scan animations, voice assistant (Web Speech API), multi-language UI (EN/ES/HI/FR), QR report, CSV export

---

## 🧱 Tech Stack

| Layer    | Technologies |
|----------|--------------|
| Frontend | React 18, Tailwind CSS 3, Framer Motion, React Router 6, Chart.js, Heroicons, Axios |
| Backend  | Python Flask 3, Flask-JWT-Extended, Flask-SQLAlchemy, Flask-CORS, ReportLab, Pillow, QRCode |
| AI (heuristic) | OpenCV, MediaPipe, Librosa |
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
│   ├── smoke_test.py             # End-to-end API test (39 checks)
│   ├── .env.example              # Environment variables template
│   ├── ml/                       # Kaggle data subsystem (no model training)
│   │   ├── data_config.py        # Dataset registry (Kaggle slugs per media type)
│   │   ├── kaggle_pipeline.py    # On-demand Kaggle fetch (temp cache, auto-clean)
│   ├── routes/
│   │   ├── auth.py               # /api/auth/*        (register, login, profile)
│   │   ├── detection.py          # /api/detect/*      (image, video, audio, text, email, social, realtime, url)
│   │   ├── history.py            # /api/history/*     (list, stats, delete)
│   │   ├── analytics.py          # /api/analytics/*   (charts + org dashboard + deepfake types)
│   │   ├── reports.py            # /api/reports/*     (pdf, csv, qr, heatmap)
│   │   ├── evidence.py           # /api/evidence/*    (cybercrime cases + blockchain ledger)
│   │   ├── keys.py               # /api/keys + /api/extend/analyze (API keys)
│   │   ├── chat.py               # /api/chat          (AI assistant)
│   │   ├── admin.py              # /api/admin/*       (users, logs, health)
│   ├── services/
│   │   ├── ai_service.py         # Orchestrator (heuristic engines + ensemble)
│   │   ├── ensemble.py           # Multi-model verdicts, trust score, XAI reasons
│   │   ├── blockchain.py         # SHA-256 evidence ledger + verification
│   │   ├── analyze_image.py      # ELA + metadata heuristics + heatmap
│   │   ├── analyze_video.py      # frame + face + temporal heuristics
│   │   ├── analyze_audio.py      # spectral / MFCC heuristics
│   │   ├── analyze_text.py       # perplexity / burstiness heuristics
│   │   ├── analyze_email.py      # phishing heuristics
│   │   ├── analyze_post.py       # image + caption social detection
│   │   └── pdf_evidence.py       # case PDF generation + email
│   ├── utils/
│   │   ├── security.py           # rate limiter, file validation, sanitizers
│   │   ├── idps.py               # intrusion detection & prevention (IP lockout, audit trail)
│   │   ├── helpers.py            # uploads, timestamps
│   │   └── report_generator.py   # PDF / CSV / QR generation
│   ├── security/logs/            # intrusion + audit JSONL trails (append-only)
│   ├── uploads/                  # Uploaded media (auto-created)
│   └── reports/                  # Generated reports (auto-created)
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
        │                         # ResultBadge, ConfidenceBar, ScanLoader, TrustScore,
        │                         # ConfidenceGauge, MultiModelVerdicts, XaiReasons,
        │                         # DeepfakeTimeline, PipelineViz, Chatbot, Leaderboard, guards…
        ├── pages/                # Home, Login, Register, Dashboard, 4 Detectors,
        │                         # RealtimeCam, EmailDetection, SocialPostDetection,
        │                         # Evidence, OrgDashboard, Results, History, Analytics,
        │                         # LearningCenter, About, Contact, Admin, Profile, ApiDocs
        └── utils/format.js       # size / date / risk formatters

└── extension/                    # Browser extension prototype (Manifest V3)
    ├── manifest.json
    ├── background.js             # context menu -> /api/extend/analyze
    ├── content.js                # inline AI badges on scanned images
    ├── popup.html / popup.js     # save API key + quick URL check
    └── icons/                    # 16/48/128 PNG icons
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
# optional, enables deeper forensic analysis + Kaggle data fetch:
pip install -r requirements-ai.txt

copy .env.example .env                   # Windows
# cp .env.example .env                   # macOS / Linux

python run.py                            # starts on http://localhost:5000
```

The first run auto-creates the SQLite database and a default admin account
(configured in `.env`, default `admin@marianalysis.local` / `Admin@12345`).

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
| POST   | `/detect/url`                  | Analyze media from a remote URL      |
| POST   | `/detect/email`                | Phishing / AI-written email scan     |
| POST   | `/detect/social`               | Image + caption social post scan     |
| POST   | `/detect/realtime`             | Live webcam frame check (not stored) |
| GET    | `/history`                     | List scans (q/type/result/page)      |
| GET    | `/history/stats`               | Dashboard summary                    |
| GET    | `/history/<id>`                | Scan detail (with XAI payload)       |
| DELETE | `/history/<id>`                | Delete scan                          |
| GET    | `/analytics/*`                 | overview, daily, weekly, fake-vs-real, by-type, activity, accuracy-trend, deepfake-types, org-dashboard, org/export |
| GET    | `/reports/<id>/pdf`            | Download PDF report                  |
| GET    | `/reports/<id>/csv`            | Export CSV report                    |
| GET    | `/reports/<id>/qr`             | QR verification image                |
| GET    | `/reports/<id>/heatmap`        | Manipulation heatmap image           |
| POST   | `/evidence/<id>/register`      | Report scan as cybercrime case + blockchain anchor |
| GET    | `/evidence/cases`              | List your reported cases             |
| GET    | `/evidence/verify/<id>`        | Verify a scan's blockchain anchor    |
| GET    | `/evidence/chain`              | Chain integrity + block summary      |
| POST   | `/evidence/<case_id>/status`   | Update case status                   |
| POST   | `/keys`                        | Create API key (returned once)       |
| GET    | `/keys`                        | List API keys                        |
| DELETE | `/keys/<id>`                   | Revoke API key                       |
| POST   | `/extend/analyze`              | Extension image check (API key auth) |
| POST   | `/chat`                        | AI assistant knowledge-base reply    |
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

## 🧠 Deepfake Analysis & the Kaggle Data Pipeline

The app ships with deterministic heuristic engines so the full pipeline works
out of the box with zero model weights. Model *training* was intentionally
removed — the Kaggle subsystem is used only to fetch/extract/use datasets
on-demand for research and validation.

### 1) Configure Kaggle credentials (once)

Get an API key at https://www.kaggle.com/settings → API, then add to `backend/.env`:

```bash
KAGGLE_USERNAME=your-username
KAGGLE_KEY=your-40-char-key
```

The pipeline writes these to `~/.kaggle/kaggle.json` automatically — no manual
re-authentication, ever.

### 2) Fetch a dataset on-demand (auto-cleaned afterwards)

```bash
cd backend
pip install -r requirements.txt -r requirements-ai.txt

python -m ml.kaggle_pipeline --image    # download + extract image dataset to temp cache
python -m ml.kaggle_pipeline --list     # show configured datasets
```

Each `--kaggle` fetch downloads the dataset **directly from Kaggle into a temp
cache, extracts it, is used, then the cache is deleted** — nothing is stored in
the project. Set `KAGGLE_AUTOSYNC=true` to auto-sync datasets at backend startup.

### 3) Live-scan reference comparison (real-time webcam / URL / extension)

When `KAGGLE_REFERENCE_ENABLED=true` (default), the first image scan pulls a
small sample of **real + fake images straight from Kaggle into a temp cache
(auto-deleted)**, builds per-class feature distributions in-process, and every
later scan — Live Webcam Check (`/detect/realtime`), URL scan (`/detect/url`)
and the browser extension (`/extend/analyze`) — is scored against those
distributions. The reference **blends 25% into the heuristic verdict** and is
reported in every result as `kaggle_reference` / `kaggle_reference_status`.

- Build runs once in the background at startup (or lazily on first scan) and is
  cached in-process — the live stream never re-downloads.
- Tune with `KAGGLE_REFERENCE_SAMPLE_SIZE` (default 10 per class) or disable
  with `KAGGLE_REFERENCE_ENABLED=false`.
- Raw dataset files never persist: only the derived in-memory statistics live
  for the life of the process.

### Available datasets (configurable in `ml/data_config.py`)

| Media | Kaggle dataset |
|-------|----------------|
| image | `ciplab/real-and-fake-face-detection` |
| video | `unidpro/deepfake-videos-dataset` |
| audio | `adarshsingh0903/audio-deepfake-detection-dataset` |
| text  | `alitaqishah/ai-vs-human-text-classification-dataset-2026` |

Add your own via `KAGGLE_EXTRA_DATASETS=user/dataset1,user/dataset2` in `.env`.

### How the heuristic engines work (no model weights needed)

- **Image**: Error Level Analysis (recompression artifacts), pHash-based
  similarity, color/texture statistics, EXIF forensics.
- **Video**: frame sampling, face detection (MediaPipe → Haar cascade fallback),
  temporal flicker, byte-hash drift.
- **Audio**: spectral flatness, zero-crossing rate, MFCC variance (librosa);
  RIFF header fallback.
- **Text**: n-gram perplexity proxy, sentence-length burstiness, repetition
  ratio.

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
- **IDPS (Intrusion Detection & Prevention)**: fail2ban-style per-IP lockout —
  5 failed logins in a window auto-bans the IP; bans + every data
  create/update/delete are written to the DB `logs` table **and** append-only
  JSONL trails in `backend/security/logs/` (intrusions.jsonl, audit.jsonl).
- **SQL Injection**: all queries are parameterized through SQLAlchemy.
- **XSS**: API returns data only; React escapes all dynamic output.
- **Uploads**: extension whitelist + magic-byte sniffing + size cap; files are
  random-renamed to prevent path traversal. Files whose content contradicts their
  extension are rejected.
- **URL scans**: http/https only, strict redirect + size + timeout limits.
- **Headers**: CSP, X-Frame-Options DENY, nosniff, no-referrer, Permissions-Policy
  and no-store cache control are set on every response.
- **Rate limiting**: in-memory sliding window per user/IP on auth + detect routes.
- **Input sanitization**: control characters stripped, length caps enforced on
  every write (auto-secured on create/edit/delete).

---

## ☁️ Deployment

### Docker (backend + frontend)

```bash
# build backend with AI deps included
docker compose build --build-arg INSTALL_AI_DEPS=1
docker compose up -d
# backend  -> http://localhost:5000
# frontend -> http://localhost:3000
```

Persistent volumes keep the SQLite DB and security/audit logs across restarts.

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
`CORS_ORIGINS=https://<frontend>.vercel.app`.

### Database hosting

- Database: use a managed MySQL (Render/Railway) or SQLite on a persistent disk.
- The heuristic engine is CPU-only — no GPU or model hosting required.

---

## 🧪 Testing

Backend end-to-end smoke test (boots the app and exercises auth, all 4 detectors,
history, analytics, reports, admin):

```bash
cd backend
python smoke_test.py        # expects 39 PASS, 0 FAIL
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
