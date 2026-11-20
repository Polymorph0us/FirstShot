from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from app.database.session import Base


class DiscoveredEvent(Base):
    __tablename__ = "discovered_events"

    id = Column(String(100), primary_key=True)  # session_id or composite id
    session_id = Column(String(50), nullable=True)
    title = Column(String(255), nullable=False)
    date = Column(String(50), nullable=False)
    start_time = Column(String(20), nullable=False)
    end_time = Column(String(20), nullable=False)
    venue = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    booking_status = Column(String(50), nullable=False)
    booking_window_start = Column(String(100), nullable=True)
    booking_window_end = Column(String(100), nullable=True)
    cancellation_deadline = Column(String(100), nullable=True)
    capacity = Column(String(50), nullable=True)
    waitlist_capacity = Column(String(50), nullable=True)
    reward_points = Column(Integer, default=0)
    attendance_cluster = Column(String(255), nullable=True)
    can_book = Column(Boolean, default=False)
    has_waitlist = Column(Boolean, default=False)
    purpose_required = Column(Boolean, default=False)
    last_seen_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "event_id": self.id,
            "session_id": self.session_id,
            "title": self.title,
            "date": self.date,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "venue": self.venue,
            "description": self.description,
            "booking_status": self.booking_status,
            "booking_window_start": self.booking_window_start,
            "booking_window_end": self.booking_window_end,
            "cancellation_deadline": self.cancellation_deadline,
            "capacity": self.capacity,
            "waitlist_capacity": self.waitlist_capacity,
            "reward_points": self.reward_points,
            "attendance_cluster": self.attendance_cluster,
            "can_book": self.can_book,
            "has_waitlist": self.has_waitlist,
            "purpose_required": self.purpose_required,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None
        }
