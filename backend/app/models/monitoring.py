from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from app.database.session import Base


class MonitoringJob(Base):
    __tablename__ = "monitoring_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    target_event_id = Column(String(100), nullable=True)  # Optional specific event
    filter_term = Column(String(50), nullable=True)
    filter_slot_name = Column(String(100), nullable=True)
    filter_date_from = Column(String(50), nullable=True)
    filter_date_to = Column(String(50), nullable=True)
    interval_seconds = Column(Integer, default=60)
    mode = Column(String(20), default="OBSERVE")  # OBSERVE or ASSIST
    is_active = Column(Boolean, default=True)
    last_checked_at = Column(DateTime, nullable=True)
    last_status = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "target_event_id": self.target_event_id,
            "filter_term": self.filter_term,
            "filter_slot_name": self.filter_slot_name,
            "filter_date_from": self.filter_date_from,
            "filter_date_to": self.filter_date_to,
            "interval_seconds": self.interval_seconds,
            "mode": self.mode,
            "is_active": self.is_active,
            "last_checked_at": self.last_checked_at.isoformat() if self.last_checked_at else None,
            "last_status": self.last_status,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(100), nullable=False)
    title = Column(String(255), nullable=False)
    status_from = Column(String(50), nullable=True)
    status_to = Column(String(50), nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_read = Column(Boolean, default=False)

    def to_dict(self):
        return {
            "id": self.id,
            "event_id": self.event_id,
            "title": self.title,
            "status_from": self.status_from,
            "status_to": self.status_to,
            "message": self.message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "is_read": self.is_read
        }
