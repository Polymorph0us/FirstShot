# Saveetha College Booking Portal — Technical Reconnaissance & Architecture

This document details the architectural reconnaissance, network protocols, DOM structure, target selection, and booking-assistance workflow for the Saveetha Engineering College Academic Events & Assessment Booking Portal (`https://learner.saveetha.in/academicevents/event-booking/`).

All credentials, session tokens, CSRF values, cookies, student names, and roll numbers have been redacted.

---

## 1. Architectural Overview

The Saveetha booking portal is a server-rendered Django application backed by Bootstrap 5 and customized administrative templates (`sb_admin`). Rather than utilizing client-side single page rendering or dynamic GraphQL/REST APIs for event grids, the core event search and listing operates via classic **Server-Side Rendering (SSR)** and standard HTML form interactions with a **Post-Redirect-Get (PRG)** pattern for booking submissions.

```
+-----------------------------------------------------------------------------------------+
|                                      User Agent / FirstShot                             |
|                                                                                         |
|  [Persistent Profile: .local/saveetha-profile/]                                         |
|         |                                                                               |
|         | 1. GET /academicevents/event-booking/?<filters>                               |
|         v                                                                               |
|  +-----------------------------------------------------------------------------------+  |
|  | Saveetha Web Server (Django)                                                      |  |
|  | - Server-Side Template Rendering                                                  |  |
|  | - Session Authentication & RBAC                                                   |  |
|  +-----------------------------------------------------------------------------------+  |
|         |                                                                               |
|         | 2. HTTP 200 (HTML with 50+ event cards)                                       |
|         v                                                                               |
|  [FirstShot SaveethaProvider]                                                           |
|    -> BeautifulSoup / DOM Parser                                                        |
|    -> Structured EventSchema Objects                                                    |
|    -> Exact Target Preference Engine (Room, Date, Time, Title)                          |
|    -> APScheduler Engine (Asia/Kolkata)                                                 |
|    -> Live Target Monitoring & Alternatives Discovery                                   |
|    -> Real-Time WebSocket Broadcast to FirstShot Dashboard                              |
|    -> Controlled Booking Assist & Confirmation Gate                                     |
+-----------------------------------------------------------------------------------------+
```

---

## 2. Assessment Booking Structure & Room Dispositions

Assessment sessions at Saveetha are structured across three primary rooms:
- **Room 1731**
- **Room 1851**
- **Room 1852**
*(Additional campus venues discovered: `1452`, `1611`, `3F - Lines Hall`).*

Each day features **four distinct assessment sessions** per room. These sessions are represented on the college website as **independent individual cards**, not as dropdown items inside a single card:
- Session 1: `08:00 AM – 09:29 AM` (Booking window opens previous evening at 7:00 PM)
- Session 2: `09:45 AM – 11:14 AM` (Booking window opens previous evening at 7:00 PM)
- Session 3: `01:15 PM – 02:44 PM` (Booking window opens previous evening at 7:00 PM)
- Session 4: `03:00 PM – 04:29 PM` (Booking window opens previous evening at 7:00 PM)

---

## 3. Target Preference Architecture (Milestone 2)

FirstShot supports exact target configurations to prevent accidental selection of wrong slots or unrelated open events:

```json
{
    "event_title": "Module Assessment",
    "target_date": "2026-11-20",
    "preferred_room": "1731",
    "preferred_start_time": "08:00",
    "preferred_end_time": "09:29",
    "accept_waitlist": false,
    "monitoring_enabled": true
}
```

### Preference Selection Methods
1. **Method A: Direct Card Selection**
   - Users browse live portal event cards in the FirstShot dashboard.
   - Clicking **"Select as Target"** automatically captures `event_id`, `room/venue`, `date`, `start_time`, `end_time`, and `title`.
   - Prevents duplicate targets (`HTTP 409 Conflict`).
2. **Method B: Manual Preference Configuration**
   - Modal interface allowing manual selection of Assessment Title, Target Date, Room, and Session.
   - Rooms are dynamically queried from live discovered data (`/api/preferences/meta/rooms`).
   - Session times are dynamically queried for that specific room and date (`/api/preferences/meta/sessions?date=...&room=...`).
   - If no matching sessions exist on that date/room, a clear notification is displayed.
   - Both methods produce the exact same underlying `BookingPreference` model.

---

## 4. Discovered Network Requests & Form Actions

### A. Sanitized Network Trace

| Timestamp | Method | Path | Resource Type | Status | Content-Type | Purpose |
|---|---|---|---|---|---|---|
| 10:33:57 | GET | `/academicevents/event-booking/` | document | 302 | `text/html` | Initial unauthenticated request |
| 10:33:57 | GET | `/sso/login/` | document | 302 | `text/html` | SSO redirect initiation |
| 10:33:58 | GET | `/authorize/` | document | 302 | `text/html` | OIDC authorization endpoint |
| 10:33:58 | GET | `/login/` | document | 200 | `text/html` | College login page |
| 10:34:35 | POST | `/login/` | document | 302 | `text/html` | Manual credential submission |
| 10:34:36 | GET | `/sso/callback/` | document | 302 | `text/html` | Token exchange |
| 10:34:37 | GET | `/academicevents/event-booking/` | document | 200 | `text/html` | Authenticated booking portal page |
| 10:34:42 | GET | `/people/sidebar-profile/` | fetch | 200 | `application/json` | Sidebar profile fetch |
| 10:34:42 | POST | `/people/host-identity/resolve/` | fetch | 200 | `application/json` | Host identity resolution |

### B. Filter Form Specification

- **Action:** `/academicevents/event-booking/`
- **Method:** `GET`
- **Form Controls:**
  - `event_term` (`select#booking-term`): Academic term ID (e.g. `16` for `26-27-EVENTDAY-02`, `11` for `26-27-LEARNING`, `""` for All).
  - `date_from` (`input#booking-date-from`): `YYYY-MM-DD`
  - `date_to` (`input#booking-date-to`): `YYYY-MM-DD`
  - `slot_name` (`input#booking-slot-name`): Text search by slot name (e.g. "Module Assessment", "VIVA").
  - `session_time` (`input#booking-session-time`): Time filter in `HH:MM` format.
  - Reset link: `<a href="/academicevents/event-booking/" class="btn btn-outline-secondary">Reset</a>`
  - Submit button: `<button type="submit" class="btn btn-primary">Apply</button>`

### C. Booking Submission Form Specification

- **Action:** `/academicevents/event-booking/` (submits to current URL)
- **Method:** `POST`
- **Form Controls:**
  - `csrfmiddlewaretoken`: Django CSRF protection token (hidden input).
  - `session_id`: Unique integer session ID (hidden input, e.g. `19824`).
  - `action`: Hidden action field (`"book"`).
  - `next`: Return URL (`"/academicevents/event-booking/"`).
  - `purpose`: Text input (`#purpose-<session_id>`) with placeholder `"Purpose for attending"`, `maxlength="255"`, marked `required`.
  - Submit buttons:
    - Normal booking: `<button type="submit" class="btn btn-primary btn-sm">Book Now</button>`
    - Waitlist booking: `<button type="submit" class="btn btn-outline-warning btn-sm">Join Waitlist</button>`
- **Post-Submission Behavior:** Server validates submission and returns `HTTP 302` redirecting back to `/academicevents/event-booking/` with Django messages framework alert.

---

## 5. Booking Status Lifecycle & Exact Monitoring

1. **`Opening Soon`** (`badge bg-info text-dark`):
   - Scheduled by administration; booking window opens in future (`booking_window_start`).
   - No booking form is rendered yet. FirstShot assigns deterministic key `evt_<date>_<time>_<venue>_<title>`.
2. **`Open`** (`badge bg-primary`):
   - Booking window is active; capacity available.
   - Form is present with `<button>Book Now</button>`.
   - **Transition Trigger:** When status changes from `Opening Soon` $\rightarrow$ `Open`:
     1. Match verified on room, date, and start time.
     2. WebSocket emits `TARGET_STATUS_CHANGED`.
     3. Notification logged in DB and displayed on dashboard.
     4. Assist Mode booking prepared automatically for review.
3. **`Waitlist Open`** (`badge bg-warning text-dark`):
   - Primary capacity is 100% full (e.g. `80/80`); waitlist has open slots (e.g. `4/5`).
   - Form is present with `<button>Join Waitlist</button>`.
4. **`Full`** (`badge bg-secondary`):
   - Both primary capacity and waitlist capacity are at 100%.
   - **Alternative Detection:** If the target becomes Full, FirstShot checks all other rooms (e.g. 1851, 1852) and times for the same date/title and reports them as separate alternatives without automatic substitution.
5. **`Booking Closed`** (`badge bg-secondary`):
   - Booking window closed or event concluded.

---

## 6. Controlled Booking Workflow (Safety Enforced)

1. **Assist Mode (Step 1 - Prepare):**
   - Click "Prepare Booking" on any available target or card.
   - Verifies authenticated session, confirms availability, extracts `session_id`, sets purpose field.
   - Displays all details in the review modal.
2. **Controlled Confirmation (Step 2 - Submit):**
   - User must review: Assessment Title, Date, Room, Time, Purpose (max 255 chars), and Booking Action.
   - User must explicitly check: `[X] I confirm that I want FirstShot to submit this booking.`
   - Submission button remains strictly disabled until confirmed.
   - Enforces duplicate submission prevention lock (`_submitting_sessions`).
   - Executes submission using authenticated browser context and CSRF verification.
   - Inspects resulting page alerts (`alert-success`, `alert-danger`, etc.) and verifies booking state.
   - Never marks a booking successful without confirmation from server response.
