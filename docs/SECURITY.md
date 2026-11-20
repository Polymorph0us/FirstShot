# FirstShot Security Architecture & Policy

> **Version:** 1.0.0  
> **Classification:** Internal / Personal Automation Security Standard

---

## 1. Threat Model & Security Boundaries

FirstShot is designed as a **single-user personal booking automation engine** operating on a trusted local workstation (Arch Linux). It interfaces with an authenticated third-party academic portal (`learner.saveetha.in`).

```
+-------------------------------------------------------------+
| WORKSTATION BOUNDARY (127.0.0.1 / localhost)                |
|                                                             |
|  +----------------+        +------------------------------+ |
|  | React Frontend |<======>| FastAPI Engine (:8000)       | |
|  +----------------+        +------------------------------+ |
|                                   |        |                |
|                     Async SQLite  |        | Playwright     |
|                                   v        v                |
|                           [firstshot.db] [.local/profile]   |
+-------------------------------------------------------------+
                                             |
                                  HTTPS (Encrypted Session)
                                             |
                                             v
                             +-------------------------------+
                             | Saveetha Learner Portal       |
                             | (learner.saveetha.in)         |
                             +-------------------------------+
```

### Security Principles:
1. **Zero External Exposure**: The FastAPI backend binds exclusively to localhost (`127.0.0.1`). It must **never** be exposed directly to the public internet without an encrypted overlay network (e.g., Tailscale).
2. **Explicit User Pre-Authorization**: The autonomous booking engine (`AUTO_BOOK`) cannot execute without explicit pre-arming and verification of user consent (`user_permitted_automation = True`).
3. **Local Credential Storage**: Authentication is maintained exclusively within a local Chromium profile (`.local/saveetha-profile/`). No plaintext passwords or tokens are stored in configuration files or code.

---

## 2. Protected Assets & Persistence

| Asset | Location | Security Measure |
|---|---|---|
| **Browser Session Profile** | `.local/saveetha-profile/` | Excluded from git via `.gitignore`. Kept in user home directory with restricted permissions. |
| **Production SQLite Database** | `backend/firstshot.db` | Excluded from git via `.gitignore`. Contains local targets and attempt logs. |
| **Environment Variables** | `.env`, `.env.local` | Excluded from git via `.gitignore`. |
| **System Daemon Unit** | `backend/firstshot.service` | Bound to `127.0.0.1:8000`. User-space systemd execution. |

---

## 3. Autonomous Execution Safeguards

To prevent unwanted, out-of-order, or duplicate booking attempts, FirstShot enforces four layers of defense:

1. **Target Execution Mutex**:
   - `_executing_targets: Set[int]` prevents concurrent redundant execution tasks for the same target slot.
2. **8-Point Preflight Engine**:
   - Checks session authentication, live portal target existence, room/date/time match, purpose string length, user consent, and prior confirmation status before initiating any request.
3. **Duplicate Prevention**:
   - The engine checks for existing `CONFIRMED` records for a target before submitting and checks portal slot state to avoid duplicate submissions.
4. **Finite Retry Window**:
   - The crash recovery loop is capped at a strict 5-minute timeout (`retry_window_seconds = 300`). If transient portal instability does not resolve within 5 minutes, execution cleanly terminates and disarms.

---

## 4. Network & Remote Access Security

### CORS Policy
- In local development mode, CORS allows local origins.
- In production, when accessed via Tailscale or reverse proxy, origins should be restricted to the specific overlay address or local port.

### Remote Access via Tailscale
- **Recommended Setup**: Run [Tailscale](https://tailscale.com) on the host workstation.
- Access the dashboard privately over the Tailscale WireGuard mesh: `http://<tailscale-ip>:8000`.
- **Prohibited**: Do NOT expose port 8000 to public DNS or router port-forwarding without authenticated reverse proxy (e.g., Caddy with mTLS / OAuth).

---

## 5. Portal Policy & Rate Limit Compliance

- FirstShot operates in compliance with standard browser interaction patterns.
- It does **not** bypass CAPTCHA, proof-of-work challenges, or credential checks.
- Dynamic polling adapts responsibly:
  - **Normal Cadence**: 60 seconds (low overhead).
  - **Near Window** (18:45–19:15): 5 seconds.
  - **Blitz Window** (18:59:45–19:05:00): 2 seconds.
- Transient HTTP 502/timeout responses are handled with a 2-second backoff.
