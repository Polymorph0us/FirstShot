# FirstShot Local Setup & Development Guide

This guide details how to set up, authenticate, and run FirstShot on your local machine (Linux/macOS).

---

## 1. System Prerequisites

- **Python**: 3.11 or higher
- **Node.js**: 20 or higher
- **npm**: 10 or higher
- **Chromium / Playwright Dependencies**:
  On Arch Linux:
  ```bash
  sudo pacman -S nss nspr alsa-lib libxss libxtst libxcomposite libxdamage libxrandr libxkbcommon pango cairo atk
  ```
  On Debian / Ubuntu:
  ```bash
  sudo apt install -y libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2
  ```

---

## 2. Backend Installation

1. Navigate to the project root and enter `backend/`:
   ```bash
   cd /home/poly/Projects/FirstShot/backend
   ```

2. Create and activate a Python virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install pinned dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Install Playwright browser binaries:
   ```bash
   playwright install chromium
   ```

---

## 3. Initial Portal Authentication

FirstShot uses a persistent Chromium profile stored in `.local/saveetha-profile/`. This preserves your login session across restarts.

1. Start the backend:
   ```bash
   PYTHONPATH=. uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
   ```

2. Launch the reauthentication browser:
   ```bash
   curl -X POST http://127.0.0.1:8000/api/session/reauthenticate
   ```
   *Alternatively, open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser, switch to **Settings**, and click **Re-authenticate in Browser**.*

3. Log in with your college credentials on the Saveetha portal. Once authenticated, close the Chromium browser window. The session cookies are saved persistently.

---

## 4. Frontend Setup & Build

1. Navigate to `frontend/`:
   ```bash
   cd /home/poly/Projects/FirstShot/frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. **Development Mode** (with hot reloading and proxy to port 8000):
   ```bash
   npm run dev
   ```
   Open [http://localhost:3000](http://localhost:3000).

4. **Production Build** (served directly by FastAPI):
   ```bash
   npm run build
   ```
   The build artifacts in `frontend/dist/` are automatically mounted by FastAPI at `http://127.0.0.1:8000/`.

---

## 5. Verification

Verify that all components are functioning correctly:

```bash
# 1. Health check
curl http://127.0.0.1:8000/health

# 2. Session verification
curl http://127.0.0.1:8000/api/session/status

# 3. Full pytest suite (26 tests)
PYTHONPATH=backend backend/.venv/bin/pytest backend/app/tests/ -v

# 4. Ruff backend lint
cd backend && .venv/bin/ruff check app/

# 5. Frontend ESLint
cd frontend && npx eslint src/
```
