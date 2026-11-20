from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.models.schemas import EventSchema


class BaseProvider(ABC):
    @abstractmethod
    async def connect(self) -> bool:
        """Initialize browser context or connection to the booking provider."""
        pass

    @abstractmethod
    async def check_session(self) -> Dict[str, Any]:
        """Check if the session is currently authenticated."""
        pass

    @abstractmethod
    async def get_events(self, filters: Optional[Dict[str, Any]] = None) -> List[EventSchema]:
        """Fetch discovered events from the provider."""
        pass

    @abstractmethod
    async def apply_filters(self, filters: Dict[str, Any]) -> List[EventSchema]:
        """Apply filters and return matching events."""
        pass

    @abstractmethod
    async def get_event_details(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Fetch detailed information for a specific event session."""
        pass

    @abstractmethod
    async def get_available_slots(self, filters: Optional[Dict[str, Any]] = None) -> List[EventSchema]:
        """Return only slots that are Open or available."""
        pass

    @abstractmethod
    async def get_booking_status(self, event_id: str) -> str:
        """Return current booking status string for an event."""
        pass

    @abstractmethod
    async def prepare_booking(self, event_id: str, purpose: str = "Academic / Career development") -> Dict[str, Any]:
        """Assist Mode: inspect and prepare booking parameters."""
        pass

    @abstractmethod
    async def submit_booking(self, session_id: str, purpose: str, action: str = "book", target_date: Optional[str] = None) -> Dict[str, Any]:
        """Execute booking submission with CSRF and verify response."""
        pass

    @abstractmethod
    async def close(self):
        """Clean up connection or browser contexts."""
        pass
