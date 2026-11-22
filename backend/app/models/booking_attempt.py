from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from app.database.session import Base


class BookingAttempt(Base):
    __tablename__ = "booking_attempts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, default=1, nullable=False, index=True)
    preference_id = Column(Integer, nullable=True)
    target_event_id = Column(String(100), nullable=True)
    session_id = Column(String(50), nullable=True)
    mode = Column(String(20), default="AUTO_BOOK")
    purpose = Column(String(255), nullable=True)
    status = Column(String(50), nullable=False, default="INITIATED")  # INITIATED, CONFIRMED, FAILED, DUPLICATE_PREVENTED, PREFLIGHT_FAILED
    verified = Column(Boolean, default=False)
    retry_count = Column(Integer, default=0)
    response_message = Column(Text, nullable=True)
    attempted_at = Column(DateTime, default=datetime.utcnow)
    execution_duration_ms = Column(Integer, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "preference_id": self.preference_id,
            "target_event_id": self.target_event_id,
            "session_id": self.session_id,
            "mode": self.mode,
            "purpose": self.purpose,
            "status": self.status,
            "verified": self.verified,
            "retry_count": self.retry_count,
            "response_message": self.response_message,
            "attempted_at": self.attempted_at.isoformat() if self.attempted_at else None,
            "execution_duration_ms": self.execution_duration_ms
        }
