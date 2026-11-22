from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from app.database.session import Base


class BookingPreference(Base):
    __tablename__ = "booking_preferences"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, default=1, nullable=False, index=True)
    event_title = Column(String(255), nullable=False)
    target_date = Column(String(50), nullable=True)          # e.g. "2026-11-20" or "Nov 20, 2026"
    preferred_room = Column(String(100), nullable=True)      # e.g. "1731", "1851", "1852"
    preferred_start_time = Column(String(20), nullable=True) # e.g. "08:00", "09:45", "13:15"
    preferred_end_time = Column(String(20), nullable=True)   # e.g. "09:29", "11:14", "14:44"
    alternative_times = Column(String(255), nullable=True)   # Comma separated
    accept_waitlist = Column(Boolean, default=False)
    monitoring_enabled = Column(Boolean, default=True)
    max_bookings = Column(Integer, default=1)
    max_attempts = Column(Integer, default=3)
    target_event_id = Column(String(100), nullable=True)     # Linked specific event card ID
    current_status = Column(String(50), nullable=True)       # e.g. "Opening Soon", "Open"
    capacity = Column(String(50), nullable=True)
    waitlist_capacity = Column(String(50), nullable=True)
    last_checked_at = Column(DateTime, nullable=True)

    # Milestone 3: Autonomous Booking Engine Fields
    booking_mode = Column(String(20), default="OBSERVE")     # OBSERVE, ASSIST, AUTO_BOOK
    is_armed = Column(Boolean, default=False)
    armed_at = Column(DateTime, nullable=True)
    purpose = Column(String(255), default="Academic Continuous Assessment")
    user_permitted_automation = Column(Boolean, default=False)
    execution_status = Column(String(50), default="IDLE")    # IDLE, ARMED, EXECUTING, SUCCESS, FAILED, DISARMED
    retry_window_seconds = Column(Integer, default=300)      # 5 minutes continuous retry window on crash/timeout
    last_preflight_status = Column(String(50), nullable=True) # PASSED, FAILED
    last_preflight_details = Column(Text, nullable=True)     # JSON string of check results
    last_preflight_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Aliases for backwards compatibility with Milestone 1
    @property
    def title(self):
        return self.event_title

    @title.setter
    def title(self, value):
        self.event_title = value

    @property
    def preferred_date(self):
        return self.target_date

    @preferred_date.setter
    def preferred_date(self, value):
        self.target_date = value

    @property
    def preferred_venue(self):
        return self.preferred_room

    @preferred_venue.setter
    def preferred_venue(self, value):
        self.preferred_room = value

    @property
    def preferred_time(self):
        return self.preferred_start_time

    @preferred_time.setter
    def preferred_time(self, value):
        self.preferred_start_time = value

    @property
    def allow_waitlist(self):
        return self.accept_waitlist

    @allow_waitlist.setter
    def allow_waitlist(self, value):
        self.accept_waitlist = value

    @property
    def is_active(self):
        return self.monitoring_enabled

    @is_active.setter
    def is_active(self, value):
        self.monitoring_enabled = value

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "event_title": self.event_title,
            "title": self.event_title,
            "target_date": self.target_date,
            "preferred_date": self.target_date,
            "preferred_room": self.preferred_room,
            "preferred_venue": self.preferred_room,
            "preferred_start_time": self.preferred_start_time,
            "preferred_time": self.preferred_start_time,
            "preferred_end_time": self.preferred_end_time,
            "alternative_times": [t.strip() for t in self.alternative_times.split(",")] if self.alternative_times else [],
            "accept_waitlist": self.accept_waitlist,
            "allow_waitlist": self.accept_waitlist,
            "monitoring_enabled": self.monitoring_enabled,
            "is_active": self.monitoring_enabled,
            "max_bookings": self.max_bookings,
            "max_attempts": self.max_attempts,
            "target_event_id": self.target_event_id,
            "current_status": self.current_status,
            "capacity": self.capacity,
            "waitlist_capacity": self.waitlist_capacity,
            "booking_mode": self.booking_mode or "OBSERVE",
            "is_armed": bool(self.is_armed),
            "armed_at": self.armed_at.isoformat() if self.armed_at else None,
            "purpose": self.purpose or "Academic Continuous Assessment",
            "user_permitted_automation": bool(self.user_permitted_automation),
            "execution_status": self.execution_status or "IDLE",
            "retry_window_seconds": getattr(self, "retry_window_seconds", 300) or 300,
            "last_preflight_status": self.last_preflight_status,
            "last_preflight_details": self.last_preflight_details,
            "last_preflight_at": self.last_preflight_at.isoformat() if self.last_preflight_at else None,
            "last_checked_at": self.last_checked_at.isoformat() if self.last_checked_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
