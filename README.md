# FirstShot

Autonomous academic assessment booking engine for the Saveetha Learner Portal (`learner.saveetha.in`).

Monitors booking windows in real-time, pre-arms for the nightly 7:00 PM IST opening, and executes a verified, authorized submission without manual intervention.

---

## Highlights

- **Pre-Armed Autonomous Execution**: Configure target slot, purpose, and room once; FirstShot automatically executes when availability opens at 7:00 PM IST.
- **5-Minute Surge-Crash Resilience**: Handles portal traffic surges (HTTP 502/timeouts) with a continuous retry loop up to 300 seconds.
- **Adaptive Cadence Polling**: Automatically ramps polling frequency from 60s idle down to 5s near-window, and 2s blitz polling at 18:59:45 IST.
- **8-Point Preflight Verification**: Audits session authentication, room match, slot existence, and duplicate prevention before any attempt.
- **Modern Minimal UI**: Dark-mode-first dashboard inspired by Linear and Vercel.
- **Live Real-Time Updates**: WebSocket broadcasts provide instant state transitions, blitz attempt counts, and confirmation notifications.

---

## Architecture & Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Backend** | Python 3.11+, FastAPI | Async REST API & WebSocket endpoints |
| **Scheduler** | APScheduler (AsyncIO) | Asia/Kolkata timezone polling engine |
| **Persistence** | SQLAlchemy 2.0 (Async) + SQLite | Local transactional target & attempt logs |
| **Migrations** | Alembic | Structured schema migrations |
| **Automation** | Playwright Chromium | Persistent browser session profile |
| **Frontend** | React 18, Vite, Lucide Icons | Minimal developer-focused dashboard |

---

## Quick Start

### 1. Prerequisites
- Python 3.11+
- Node.js 20+
- Chromium (installed via Playwright)

### 2. Backend Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 3. Launch Development Server

```bash
PYTHONPATH=. uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

The dashboard will be available at [http://127.0.0.1:8000](http://127.0.0.1:8000).

### 4. Authenticate College Account

On first launch, click **Re-authenticate in Browser** in the dashboard settings, or invoke:

```bash
curl -X POST http://127.0.0.1:8000/api/session/reauthenticate
```

Log in manually to Saveetha Learner Portal in the Chromium window that appears. Your session cookies will be stored persistently in `.local/saveetha-profile/` and reused automatically.

### 5. Frontend Development & Build

```bash
cd frontend
npm install
npm run dev    # Vite dev server on http://localhost:3000

# For production build:
npm run build  # Builds to frontend/dist/ (served directly by FastAPI)
```

---

## Test Suite

FirstShot includes 26 unit and integration tests covering extraction, target matching, safety preflights, crash resilience, and simulated autonomous executions:

```bash
PYTHONPATH=backend backend/.venv/bin/pytest backend/app/tests/ -v
```

---

## Documentation

- [Codebase Audit Report](docs/CODEBASE_AUDIT.md)
- [System Architecture](docs/ARCHITECTURE.md)
- [Local Setup Guide](docs/LOCAL_SETUP.md)
- [Deployment Guide (systemd & Tailscale)](docs/DEPLOYMENT.md)
- [Security Model & Safeguards](docs/SECURITY.md)
- [Release Report 1.0](docs/RELEASE_REPORT.md)

---

## License

Personal Automation Platform. Created for academic workflow automation.
