from app.providers.saveetha import SaveethaProvider

SAMPLE_CARD_HTML = """
<div class="card shadow-sm border-0 h-100">
 <div class="card-body d-flex flex-column gap-3">
  <div class="d-flex justify-content-between align-items-start gap-2">
   <div>
    <h5 class="fw-semibold mb-1">Module Assessment</h5>
    <div class="text-muted small">Nov 19, 2026 · 8 a.m. - 9:29 a.m.</div>
    <div class="text-muted small">Venue: 1731</div>
   </div>
   <div class="text-end">
    <span class="badge bg-secondary">Booking Closed</span>
   </div>
  </div>
  <div class="d-flex flex-column gap-2">
   <div class="d-flex flex-wrap gap-2">
    <span class="badge bg-warning text-dark">ClassAttendance: None</span>
    <span class="badge bg-success">Reward Points: 0</span>
   </div>
   <div class="small text-muted">Booking Window: Nov 18, 2026, 7 p.m. → Nov 19, 2026, 8 a.m.</div>
   <div class="small text-muted">Cancellation Ends: Nov 19, 2026, 6 a.m.</div>
   <div class="small text-muted">Capacity: 80/80</div>
   <div class="small text-muted">Waitlist: 2/5</div>
  </div>
  <div class="mt-auto"></div>
 </div>
</div>

<div class="card shadow-sm border-0 h-100">
 <div class="card-body d-flex flex-column gap-3">
  <div class="d-flex justify-content-between align-items-start gap-2">
   <div>
    <h5 class="fw-semibold mb-1">Open Tech Workshop</h5>
    <div class="text-muted small">Nov 20, 2026 · 1:15 p.m. - 2:44 p.m.</div>
    <div class="text-muted small">Venue: Lab 3</div>
   </div>
   <div class="text-end">
    <span class="badge bg-primary">Open</span>
   </div>
  </div>
  <div class="d-flex flex-column gap-2">
   <div class="d-flex flex-wrap gap-2">
    <span class="badge bg-success">Reward Points: 10</span>
   </div>
   <div class="small text-muted">Booking Window: Nov 19, 2026, 10 a.m. → Nov 20, 2026, 1 p.m.</div>
   <div class="small text-muted">Capacity: 20/50</div>
  </div>
  <div class="mt-auto">
   <form method="post">
    <input type="hidden" name="session_id" value="99901"/>
    <input type="hidden" name="action" value="book"/>
    <input type="text" name="purpose" placeholder="Purpose for attending" required/>
    <button type="submit" class="btn btn-primary btn-sm">Book Now</button>
   </form>
  </div>
 </div>
</div>
"""

def test_extract_events():
    events = SaveethaProvider.parse_events_html(SAMPLE_CARD_HTML)
    assert len(events) == 2

    # Card 1 (Closed)
    c1 = events[0]
    assert c1.title == "Module Assessment"
    assert c1.date == "Nov 19, 2026"
    assert c1.start_time == "08:00"
    assert c1.end_time == "09:29"
    assert c1.venue == "1731"
    assert c1.booking_status == "Booking Closed"
    assert c1.capacity == "80/80"
    assert c1.waitlist_capacity == "2/5"
    assert c1.can_book is False
    assert c1.has_waitlist is False

    # Card 2 (Open)
    c2 = events[1]
    assert c2.title == "Open Tech Workshop"
    assert c2.session_id == "99901"
    assert c2.start_time == "13:15"
    assert c2.end_time == "14:44"
    assert c2.venue == "Lab 3"
    assert c2.booking_status == "Open"
    assert c2.reward_points == 10
    assert c2.can_book is True
    assert c2.purpose_required is True

def test_date_time_normalization():
    assert SaveethaProvider._normalize_time("8 a.m.") == "08:00"
    assert SaveethaProvider._normalize_time("1:15 p.m.") == "13:15"
    assert SaveethaProvider._normalize_time("11:30 a.m.") == "11:30"
    assert SaveethaProvider._normalize_time("9:29 a.m.") == "09:29"

    assert "2026-11-18 19:00" in SaveethaProvider._normalize_datetime("Nov 18, 2026, 7 p.m.")
    assert "2026-11-19 08:00" in SaveethaProvider._normalize_datetime("Nov 19, 2026, 8 a.m.")
