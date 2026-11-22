# firstshot

autonomous booking bot for the saveetha learner portal (`learner.saveetha.in`).

arms your assessment target before 7pm, verifies availability, and books it the second the window drops without you needing to click anything. if the site crashes or throws 502s under surge traffic, it keeps hammering for 5 minutes straight until you're booked.

---

## setup

### 1. install stuff

clone the repo and set up the backend:

```bash
git clone https://github.com/your-username/FirstShot.git
cd FirstShot/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

build the frontend (one time):

```bash
cd ../frontend
npm install
npm run build
```

### 2. run the app

from the backend directory:

```bash
cd ../backend
source .venv/bin/activate
PYTHONPATH=. uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 3. sign in & connect your college portal

1. open [http://localhost:8000](http://localhost:8000) in your browser.
2. the app will ask for authentication. create an account or sign in with your username and password.
3. once you're in, connect your saveetha portal session:
   - click the portal status badge in the top right or head over to the settings tab.
   - hit **interactive remote portal login**.
   - an in-browser window will stream directly onto your screen. log in with your saveetha roll number and password.
   - your session cookies are automatically saved to your own isolated profile. you never have to type your password again.
4. you are all set.

---

## how to use it

### 1. pick your target slot
- go to the **targets** or **overview** tab.
- you can browse live portal sessions and click **save as target**, or manually add the exact slot you want (title, date, room like `1731`, start time like `08:00`).

### 2. pre-arm the booking
- on your saved target, hit **pre-arm auto-book**.
- type your booking purpose (e.g. `academic assessment`).
- toggle waitlist if you want it to grab waitlist when the room fills up.
- check the box confirming you authorize the automated attempt.
- click **confirm & arm**.
- firstshot runs an 8-point preflight check right away (verifies your portal session, checks the room match, confirms slot existence, and prevents duplicate attempts).

### 3. let it cook
- you don't have to touch anything when 7pm hits.
- at 6:59:45 pm ist, it kicks into blitz mode, checking every 2 seconds.
- at 7:00:00 pm ist, the moment the slot turns open, it submits the booking immediately.
- if the portal crashes or times out (classic 502 / bad gateway), firstshot doesn't give up. it enters a continuous 5-minute surge retry loop and keeps retrying every 2s until it gets a confirmed booking.
- check the **activity** tab to see real-time attempts, status transitions, and verification logs.

---

## features

- **pre-armed autonomous booking**: set your room, date, and purpose beforehand. when 7pm drops, it books automatically. no manual clicking needed.
- **5-minute crash surge loop**: the portal always dies at 7:00 pm. firstshot catches timeouts, 500s, 502s, and connection drops and retries continuously for 300 seconds until the server recovers and books your slot.
- **isolated multi-user browser profiles**: each student gets their own independent chromium profile under `.local/profiles/user_<id>`. your cookies, session, targets, and booking history are completely separated from everyone else.
- **remote interactive browser login**: log into the portal directly through an interactive canvas stream in your web browser. no display server, no host windows popping up on someone's screen, and zero plaintext passwords stored.
- **adaptive blitz polling**: chills at 60s during the day, drops to 5s near the window, and goes into 2s blitz mode right at 18:59:45 ist.
- **8-point preflight safety audit**: validates session auth, room/time matching, purpose limits, and already-booked protection so you don't waste attempts on invalid slots.
- **minimal dark ui**: clean, fast interface inspired by linear and raycast. live websocket notifications for attempt counts, status changes, and confirmations.
- **full test suite**: 33 unit and integration tests covering multi-user isolation, target matching, autonomous execution, and failure recovery.

---

## tests

to run the full test suite:

```bash
cd backend
source .venv/bin/activate
pytest -v
```
