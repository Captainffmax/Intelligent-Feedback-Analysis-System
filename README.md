# Intelligent Feedback Analysis System (IFAS)

An AI-powered platform that collects student feedback on academic and campus services, analyses it automatically, and turns it into decisions administrators can act on.

Students submit feedback from a mobile-friendly Progressive Web App (PWA) that keeps working offline. Each submission passes through a four-tier AI pipeline that cleans the text, classifies its sentiment, extracts its key themes and stores the result in MongoDB. Administrators use an analytics dashboard to filter the results, track trends, and generate a Gemini-written action summary for any department.

**Quick links:** [Installation](#installation) · [Running the System](#running-the-system) · [Using the System](#using-the-system) · [Troubleshooting](#troubleshooting)

---

## Table of Contents

1. [Introduction](#introduction)
2. [Key Features](#key-features)
3. [System Architecture](#system-architecture)
4. [The AI Pipeline](#the-ai-pipeline)
5. [Technology Stack](#technology-stack)
6. [Project Structure](#project-structure)
7. [Database Schema](#database-schema)
8. [API Endpoints](#api-endpoints)
9. [Requirements](#requirements)
10. [Installation](#installation)
11. [Running the System](#running-the-system)
12. [Using the System](#using-the-system)
13. [Configuration Reference](#configuration-reference)
14. [Troubleshooting](#troubleshooting)
15. [Security Notes](#security-notes)

---

## Introduction

Higher education institutions collect large volumes of student feedback on teaching, administration, hostels, internet access, the library and other services. Most of it is unstructured text, and analysing it by hand is slow, subjective and rarely done in time to act on.

IFAS automates that analysis. It:

- **collects** feedback through a lightweight app that works on low-bandwidth campus networks and offline;
- **analyses** every comment the moment it arrives, labelling its sentiment (Positive, Neutral or Negative) and extracting its main themes;
- **presents** the results on a dashboard where administrators can filter by department, service category, sentiment and date;
- **summarises** clusters of negative feedback into short, prioritised action points using Google Gemini.

The system handles Nigerian Pidgin, slang, sarcasm and mixed opinions, which standard English sentiment models misclassify, by escalating uncertain cases to Gemini for a second opinion.

---

## Key Features

**For students**
- Installable PWA that runs on any phone or laptop browser
- One-time profile (name, matriculation number, department)
- Ten service categories, plus a free-text "Other"
- Optional anonymous submission
- Instant sentiment result after submitting
- Offline queue: feedback written without internet is stored on the device and sent automatically when the connection returns

**For administrators**
- Secure login (bcrypt-hashed passwords, JWT sessions)
- KPI cards with sparklines, sentiment trends over time, category breakdown and top keywords
- "Needs attention" panel highlighting the most negative areas
- Filters by department, category, sentiment and date range
- Searchable "All Feedback" view showing each comment with its sentiment and keywords
- One-click Gemini action summary for a department's negative feedback
- Light and dark themes

---

## System Architecture

The system has three independent components that share one MongoDB database.

```
  ┌────────────────────┐        POST /api/feedback        ┌──────────────────────────┐
  │  Student PWA        │ ───────────────────────────────▶ │  FastAPI Backend          │
  │  React + Vite       │ ◀─────────────────────────────── │  (port 8000)              │
  │  offline queue      │      sentiment + keywords        │                           │
  └────────────────────┘                                   │  AI Engine                │
                                                           │   Tier A  spaCy           │
                                                           │   Tier B  DistilBERT ──┐  │
                                                           │   Tier C  KeyBERT      │  │
                                                           │   Tier D  Gemini ◀─────┘  │
                                                           └────────────┬─────────────┘
                                                                        │ single write
                                                                        ▼
  ┌────────────────────┐     reads (aggregation)          ┌──────────────────────────┐
  │  Admin Dashboard    │ ───────────────────────────────▶ │  MongoDB                  │
  │  Streamlit          │                                  │  feedback_analysis_db     │
  │  (port 8501)        │ ── login / summarize ──▶ Backend └──────────────────────────┘
  └────────────────────┘
```

- In production the backend also serves the compiled student app, so students and the API share one address (`http://<server>:8000`) and no rebuild is needed when the network changes.
- The dashboard reads MongoDB directly for analytics, and calls the backend only to log in and to request Gemini summaries.

---

## The AI Pipeline

Every submission runs through Tiers A to C before it is saved. Tier D is used for sentiment escalation and on request from the dashboard.

| Tier | Model | Purpose |
|------|-------|---------|
| **A** | spaCy `en_core_web_sm` | Normalises the text (lower-casing, removing punctuation and stop words). The cleaned text is kept for audit. |
| **B** | DistilBERT `distilbert-base-uncased-finetuned-sst-2-english` | Classifies sentiment as POSITIVE or NEGATIVE with a confidence score. Results below the neutral threshold (0.60) become NEUTRAL. |
| **C** | KeyBERT + Sentence-Transformers | Extracts up to five key phrases (e.g. "slow internet") with relevance scores. |
| **D** | Google Gemini (`gemini-3.6-flash`) | (1) Gives a second opinion on uncertain sentiment; (2) writes action summaries for administrators. |

**Important design decisions**

- **Tiers B and C read the original text, not the cleaned text.** Stop-word removal deletes negations ("not", "without"), which would invert the sentiment.
- **Escalation to Gemini.** A Tier B result is re-checked by Gemini when DistilBERT's confidence is below 0.75, when the label is POSITIVE (to catch sarcasm), when the comment contrasts two opinions ("but", "however"), or when it contains Nigerian Pidgin/slang ("wahala", "omo", "abeg", …). Gemini's label then replaces DistilBERT's.
- **Mixed opinions are NEUTRAL.** A comment that praises one thing and criticises another is labelled NEUTRAL, applied last so the result does not depend on Gemini being reachable.
- **Graceful degradation.** If Gemini is slow (over 8 s), rate-limited or offline, the DistilBERT label is kept and the submission still succeeds.

---

## Technology Stack

| Layer | Technologies |
|-------|--------------|
| Student app | React 18, Vite 5, Tailwind CSS 3, React Router, Axios, Workbox (service worker), IndexedDB (`idb`) |
| Backend API | Python 3.12/3.13, FastAPI, Uvicorn, Pydantic v2, pydantic-settings |
| AI / NLP | spaCy, Hugging Face Transformers, PyTorch, KeyBERT, Sentence-Transformers, Google Generative AI SDK |
| Database | MongoDB (Motor async driver for the backend, PyMongo for the dashboard) |
| Security | bcrypt password hashing, JSON Web Tokens (python-jose) |
| Dashboard | Streamlit, Pandas, Chart.js |

---

## Project Structure

```
Intelligent-Feedback-Analysis-System/
├── backend/                         FastAPI REST API + AI engine
│   ├── app/
│   │   ├── main.py                  API routes, start-up, serves the built PWA
│   │   ├── config.py                Settings loaded from .env
│   │   ├── database.py              Async MongoDB connection (Motor)
│   │   ├── models.py                Pydantic schemas (Student, Feedback, Administrator)
│   │   ├── auth.py                  bcrypt hashing + JWT issue/verify
│   │   └── services/
│   │       └── ai_engine.py         Four-tier AI pipeline (Tiers A–D)
│   ├── scripts/
│   │   └── seed.py                  Creates the admin account + sample data
│   ├── requirements.txt
│   └── .env.example                 Configuration template
│
├── admin-dashboard/                 Streamlit analytics dashboard
│   ├── app.py                       Dashboard pages, filters, Gemini summary
│   ├── components/charts.py         Chart.js chart builders
│   ├── .streamlit/config.toml       Streamlit theme/server settings
│   ├── requirements.txt
│   └── .env.example
│
├── frontend-pwa/                    Student Progressive Web App
│   ├── src/
│   │   ├── App.jsx, main.jsx        App shell and routing
│   │   ├── sw.js, registerSW.js     Service worker (offline support)
│   │   ├── profile.js               Locally stored student profile
│   │   ├── api/client.js            HTTP client for the backend
│   │   ├── db/offlineQueue.js       IndexedDB queue for offline submissions
│   │   ├── hooks/useNetworkStatus.js
│   │   ├── components/FeedbackForm.jsx
│   │   └── pages/HomePage.jsx, ProfilePage.jsx
│   ├── public/                      Icons, images, fonts
│   ├── package.json
│   ├── vite.config.js
│   └── .env.example
│
├── start.bat / start.sh             Development mode (this machine only)
├── deploy.bat / deploy.sh           Production mode (whole network)
├── build-frontend.bat / .sh         Compiles the student app
├── stop.bat                         Stops all services (Windows)
├── tunnel.sh                        Public HTTPS links via Cloudflare (Linux)
└── READ-ME-FIRST.txt                Short Windows setup checklist
```

---

## Database Schema

Database: `feedback_analysis_db` (MongoDB). The AI outputs are embedded inside each feedback document, so a submission is stored in one write with no joins.

| Collection | Fields |
|------------|--------|
| `students` | `_id`, `student_id`, `name`, `department`, `email` |
| `feedback` | `_id`, `student_id`, `student_name`, `department`, `category`, `custom_category`, `feedback_text`, `date_submitted`, `sentiment_analysis { label, confidence_score, source }`, `keywords_extracted [ { keyword, relevance_score } ]` |
| `administrators` | `_id`, `username`, `password` (bcrypt hash), `role` |

Example feedback document:

```json
{
  "student_id": "CSC/2021/001",
  "student_name": "Amara Okeke",
  "department": "Computer Science",
  "category": "Wi-Fi",
  "feedback_text": "The internet connectivity in the ICT laboratory is very poor and keeps disconnecting.",
  "date_submitted": "2026-09-15T10:24:00Z",
  "sentiment_analysis": { "label": "NEGATIVE", "confidence_score": 0.98, "source": "distilbert" },
  "keywords_extracted": [
    { "keyword": "internet connectivity", "relevance_score": 0.71 },
    { "keyword": "ict laboratory", "relevance_score": 0.58 }
  ]
}
```

Service categories: Hostel, Wi-Fi, Library, ICT, Teaching, Registration, Examination, Counseling, Administration, Other.

---

## API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/health` | — | Database connectivity and AI-engine readiness |
| POST | `/api/feedback` | — | Submit feedback; returns sentiment and keywords |
| POST | `/api/admin/login` | — | Administrator login (form fields `username`, `password`); returns a JWT |
| POST | `/api/admin/summarize` | JWT | Gemini action summary for a department's negative comments |
| GET | `/docs` | — | Interactive Swagger API documentation |

---

## Requirements

| Requirement | Version / notes |
|-------------|-----------------|
| Operating system | Windows 10/11, Ubuntu 22.04+, or macOS |
| Python | 3.12 or 3.13 |
| Node.js | 18 LTS or newer (includes npm) |
| MongoDB | Community Server (run as a service) or a MongoDB Atlas cluster |
| Memory / disk | 8 GB RAM recommended; ~8 GB free disk (Python environment ≈ 6.5 GB) |
| Internet | Needed on first run (~3 GB of packages and AI models) and for Gemini |
| Gemini API key | Free from [Google AI Studio](https://aistudio.google.com/) |

---

## Installation

### 1. Get the code

```bash
git clone https://github.com/Captainffmax/Intelligent-Feedback-Analysis-System.git
cd Intelligent-Feedback-Analysis-System
```

On Windows, place the folder in a short path without spaces (e.g. `C:\IFAS`) and **not** inside OneDrive, which corrupts the Python environment while it is being built.

### 2. Create the Python environment

One virtual environment, inside `backend/`, is shared by the backend and the dashboard.

**Windows**
```bat
cd backend
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r ..\admin-dashboard\requirements.txt
python -m spacy download en_core_web_sm
```

**Linux / macOS**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r ../admin-dashboard/requirements.txt
python -m spacy download en_core_web_sm
```

Check it worked:
```bash
python -c "import uvicorn, streamlit, spacy; print('all libraries OK')"
```

### 3. Configure the environment files

Copy each template and fill in your values:

| Template | Copy to |
|----------|---------|
| `backend/.env.example` | `backend/.env` |
| `admin-dashboard/.env.example` | `admin-dashboard/.env` |
| `frontend-pwa/.env.example` | `frontend-pwa/.env.local` (optional) |

At minimum, set these in `backend/.env`:

```ini
MONGO_URI=mongodb://127.0.0.1:27017          # or your Atlas connection string
MONGO_DB_NAME=feedback_analysis_db
GEMINI_API_KEY=your_gemini_api_key
JWT_SECRET_KEY=your_64_char_hex_secret       # python -c "import secrets; print(secrets.token_hex(32))"
SEED_ADMIN_USERNAME=admin
SEED_ADMIN_PASSWORD=choose_a_strong_password
```

and in `admin-dashboard/.env`:

```ini
MONGO_URI=mongodb://127.0.0.1:27017
MONGO_DB_NAME=feedback_analysis_db
BACKEND_API_URL=http://localhost:8000
```

See [Configuration Reference](#configuration-reference) for every setting.

### 4. Create the administrator account

MongoDB must be running. From `backend/` with the virtual environment active:

```bash
python -m scripts.seed --reset
```

This creates the administrator from `SEED_ADMIN_USERNAME` / `SEED_ADMIN_PASSWORD`, a small student roster and ten sample feedback records analysed by the real AI pipeline. 

> **Warning:** `--reset` deletes **all** administrators, students and feedback first. Use it only on a fresh install. Without `--reset` the script is safe to run repeatedly and keeps existing data.

### 5. Build the student app

**Windows:** double-click `build-frontend.bat`
**Linux / macOS:** `./build-frontend.sh`

Or manually:
```bash
cd frontend-pwa
npm install
npm run build
```

The compiled app is written to `frontend-pwa/dist/`, which the backend serves automatically.

---

## Running the System

### Option A — Production (whole network)

Serves the compiled student app and the dashboard to every device on the same Wi-Fi.

| | Windows | Linux / macOS |
|--|---------|---------------|
| Start | Right-click `deploy.bat` → **Run as administrator** | `./deploy.sh` |
| Stop | Double-click `stop.bat` | `./deploy.sh stop` |

Wait until the backend window shows **"Application startup complete"**. The AI models take 1–4 minutes to load on the first run. The launcher prints the addresses:

| Service | Address |
|---------|---------|
| Student app | `http://<server-IP>:8000` |
| Admin dashboard | `http://<server-IP>:8501` |
| API docs | `http://<server-IP>:8000/docs` |

### Option B — Development (this machine only)

Runs the student app with live reload through the Vite dev server.

| | Windows | Linux / macOS |
|--|---------|---------------|
| Start | Double-click `start.bat` | `./start.sh` |
| Stop | Double-click `stop.bat` | `./start.sh stop` |

| Service | Address |
|---------|---------|
| Student app (dev) | `http://localhost:5173` |
| Admin dashboard | `http://localhost:8501` |
| Backend / API docs | `http://localhost:8000/docs` |

> `start.sh` starts the backend and dashboard only. Run `cd frontend-pwa && npm run dev` in a second terminal for the student app on port 5173.

### Option C — Manual (three terminals)

```bash
# Terminal 1 — backend (virtual environment active)
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Terminal 2 — dashboard (virtual environment active)
cd admin-dashboard
streamlit run app.py --server.port 8501

# Terminal 3 — student app with live reload (optional)
cd frontend-pwa
npm run dev
```

### Optional — public HTTPS link (Linux)

With the system running, `./tunnel.sh` opens free Cloudflare quick-tunnel links (`https://….trycloudflare.com`) so the app can be reached from outside the local network. Requires `cloudflared`. `./tunnel.sh url` reprints the links and `./tunnel.sh stop` closes them. The address changes on every run. Installing the PWA and its offline mode need HTTPS on devices other than the server, so use a tunnel link when testing on phones.

---

## Using the System

### Students

1. Open the student app address. On a phone, choose **Add to Home Screen** to install it.
2. Fill in your profile once: full name, matriculation number and department.
3. Tap to give feedback, choose a service category (or "Other" and type your own), and write your comment.
4. Optionally tick **Submit anonymously** to withhold your name and matriculation number.
5. Submit. The detected sentiment is shown immediately. If you are offline, the feedback is queued and sent automatically when you reconnect.

### Administrators

1. Open the dashboard address and log in.
2. **Dashboard** view: KPIs, sentiment trend, category breakdown, top keywords and areas needing attention.
3. Use the sidebar filters: department, service category, sentiment, date range.
4. **All Feedback** view: search and read individual comments with their sentiment and keywords.
5. **Generate Action Summary**: enter the department or unit under review to get a Gemini-written summary of its negative feedback with recommended actions.
6. **Log out** from the sidebar when finished.

---

## Configuration Reference

`backend/.env`

| Variable | Default | Description |
|----------|---------|-------------|
| `MONGO_URI` | — (required) | MongoDB connection string |
| `MONGO_DB_NAME` | `feedback_analysis_db` | Database name |
| `MONGO_TIMEOUT_MS` | `5000` | Connection timeout; fails fast on unstable networks |
| `GEMINI_API_KEY` | empty | Google Gemini key; without it Tier D is disabled |
| `GEMINI_MODEL` | `gemini-3.6-flash` | Gemini model name |
| `GEMINI_SENTIMENT_FALLBACK` | `true` | Escalate uncertain sentiment to Gemini |
| `SENTIMENT_ESCALATE_THRESHOLD` | `0.75` | DistilBERT confidence below which Gemini is consulted |
| `GEMINI_TIMEOUT_SECONDS` | `8.0` | Maximum wait for an escalation before keeping the DistilBERT label |
| `SENTIMENT_MODEL` | `distilbert-base-uncased-finetuned-sst-2-english` | Hugging Face sentiment model |
| `NEUTRAL_THRESHOLD` | `0.60` | Confidence below which a label becomes NEUTRAL |
| `SPACY_MODEL` | `en_core_web_sm` | spaCy model for Tier A |
| `JWT_SECRET_KEY` | — | Secret used to sign admin tokens (change it) |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `JWT_EXPIRE_MINUTES` | `480` | Admin session length (8 hours) |
| `SEED_ADMIN_USERNAME` / `_PASSWORD` / `_ROLE` | `admin` / — / `ICT Admin` | Account created by `scripts/seed.py` |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Browser origins allowed to call the API (only the Vite dev server needs one) |

`admin-dashboard/.env`: `MONGO_URI`, `MONGO_DB_NAME`, `BACKEND_API_URL` (default `http://localhost:8000`).

`frontend-pwa/.env.local`: `VITE_API_BASE_URL` (default `/api`; leave it unset for production builds).

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Backend takes minutes to start | Normal on first run while the AI models download and load. Wait for "Application startup complete", or check `GET /health` until `ai_engine_ready` is `true`. |
| `MongoDB connection failed` | Start MongoDB (Windows: run `deploy.bat` as administrator, or `net start MongoDB`; Linux: `sudo systemctl start mongod`). Check `MONGO_URI`. |
| Phones cannot reach the app | Both devices must be on the same network. Allow TCP ports 8000 and 8501 through the firewall (Windows: `netsh advfirewall firewall add rule name="IFAS" dir=in action=allow protocol=TCP localport=8000`, and the same for 8501). Never open port 27017. |
| "The student app has not been built yet" | Run `build-frontend.bat` / `./build-frontend.sh` first. |
| Gemini summary fails / sentiment not escalated | Check `GEMINI_API_KEY`. The free tier allows about **5 requests per minute** and a small daily quota; escalations also use this quota. Wait a minute, or enable billing on the key. Submissions still succeed using the DistilBERT label. |
| Login rejected after changing the password in `.env` | Re-run `python -m scripts.seed` to update the stored administrator. |
| `ModuleNotFoundError` | Activate the virtual environment (`backend/.venv`) before running Python commands. |

---

## Security Notes

- `backend/.env` contains the Gemini key, the JWT secret and the admin password. It is excluded by `.gitignore`: never commit, email or screenshot it. Share `.env.example` instead.
- Administrator passwords are stored only as bcrypt hashes; dashboard sessions use signed JWTs that expire after 8 hours.
- Anonymous submissions are stored with `student_id = "ANONYMOUS"` and no name.
- The MongoDB port (27017) has no password in the default local setup; do not expose it to the network.
