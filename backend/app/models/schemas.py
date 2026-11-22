from typing import List, Optional

from pydantic import BaseModel, Field


class EventSchema(BaseModel):
    event_id: str
    session_id: Optional[str] = None
    title: str
    date: str
    start_time: str
    end_time: str
    venue: Optional[str] = None
    description: Optional[str] = None
    booking_status: str
    booking_window_start: Optional[str] = None
    booking_window_end: Optional[str] = None
    cancellation_deadline: Optional[str] = None
    capacity: Optional[str] = None
    waitlist_capacity: Optional[str] = None
    reward_points: int = 0
    attendance_cluster: Optional[str] = None
    can_book: bool = False
    has_waitlist: bool = False
    purpose_required: bool = False
    matched: bool = False
    match_score: int = 0
    match_reasons: List[str] = Field(default_factory=list)

class FilterParams(BaseModel):
    event_term: Optional[str] = ""
    date_from: Optional[str] = ""
    date_to: Optional[str] = ""
    slot_name: Optional[str] = ""
    session_time: Optional[str] = ""

class PreferenceCreate(BaseModel):
    # Backward compatible fields
    title: Optional[str] = None
    event_title: Optional[str] = None
    preferred_date: Optional[str] = None
    target_date: Optional[str] = None
    preferred_time: Optional[str] = None
    preferred_start_time: Optional[str] = None
    preferred_end_time: Optional[str] = None
    alternative_times: Optional[List[str]] = Field(default_factory=list)
    preferred_venue: Optional[str] = None
    preferred_room: Optional[str] = None
    max_bookings: int = 1
    allow_waitlist: Optional[bool] = None
    accept_waitlist: bool = False
    max_attempts: int = 3
    is_active: Optional[bool] = None
    monitoring_enabled: bool = True
    target_event_id: Optional[str] = None

class PreferenceResponse(BaseModel):
    id: int
    user_id: Optional[int] = 1
    event_title: str
    title: str
    target_date: Optional[str] = None
    preferred_date: Optional[str] = None
    preferred_room: Optional[str] = None
    preferred_venue: Optional[str] = None
    preferred_start_time: Optional[str] = None
    preferred_time: Optional[str] = None
    preferred_end_time: Optional[str] = None
    alternative_times: List[str] = Field(default_factory=list)
    accept_waitlist: bool = False
    allow_waitlist: bool = False
    monitoring_enabled: bool = True
    is_active: bool = True
    max_bookings: int = 1
    max_attempts: int = 3
    target_event_id: Optional[str] = None
    current_status: Optional[str] = None
    capacity: Optional[str] = None
    waitlist_capacity: Optional[str] = None
    booking_mode: str = "OBSERVE"
    is_armed: bool = False
    armed_at: Optional[str] = None
    purpose: Optional[str] = "Academic Continuous Assessment"
    user_permitted_automation: bool = False
    execution_status: str = "IDLE"
    retry_window_seconds: int = 300
    last_preflight_status: Optional[str] = None
    last_preflight_details: Optional[str] = None
    last_preflight_at: Optional[str] = None
    last_checked_at: Optional[str] = None
    created_at: Optional[str] = None

class TargetSlotFromCard(BaseModel):
    event_id: str
    title: str
    date: str
    start_time: str
    end_time: Optional[str] = None
    venue: str
    accept_waitlist: bool = False
    monitoring_enabled: bool = True

class TargetSlotEdit(BaseModel):
    event_title: Optional[str] = None
    target_date: Optional[str] = None
    preferred_room: Optional[str] = None
    preferred_start_time: Optional[str] = None
    preferred_end_time: Optional[str] = None
    accept_waitlist: Optional[bool] = None
    monitoring_enabled: Optional[bool] = None

class MonitoringJobCreate(BaseModel):
    name: str
    target_event_id: Optional[str] = None
    filter_term: Optional[str] = ""
    filter_slot_name: Optional[str] = ""
    filter_date_from: Optional[str] = ""
    filter_date_to: Optional[str] = ""
    interval_seconds: int = 60
    mode: str = "OBSERVE"  # OBSERVE or ASSIST

class MonitoringJobResponse(MonitoringJobCreate):
    id: int
    is_active: bool
    last_checked_at: Optional[str] = None
    last_status: Optional[str] = None

class SessionStatusResponse(BaseModel):
    authenticated: bool
    username_or_role: Optional[str] = None
    profile_dir: str
    portal_url: str
    message: str

class PrepareBookingRequest(BaseModel):
    event_id: str
    purpose: Optional[str] = "Academic Continuous Assessment"

class PrepareBookingResponse(BaseModel):
    event_id: str
    session_id: str
    title: str
    venue: Optional[str]
    date: Optional[str] = None
    time: Optional[str] = None
    booking_action: str
    purpose: str
    ready_to_submit: bool
    status: str
    message: str

class ConfirmBookingRequest(BaseModel):
    event_id: str
    session_id: str
    purpose: str
    booking_action: str = "book"  # "book" or "join_waitlist"
    user_confirmed: bool = False

class ConfirmBookingResponse(BaseModel):
    success: bool
    event_id: str
    session_id: str
    title: str
    booking_action: str
    status: str
    message: str
    timestamp: str
    verified: bool = False

class AlternativeSession(BaseModel):
    event_id: str
    title: str
    date: str
    start_time: str
    end_time: str
    venue: str
    booking_status: str
    capacity: Optional[str] = None
    waitlist_capacity: Optional[str] = None
    can_book: bool = False
    has_waitlist: bool = False
    reason: str

# Milestone 3: Autonomous Booking Engine Schemas
class SetModeRequest(BaseModel):
    booking_mode: str  # "OBSERVE", "ASSIST", "AUTO_BOOK"

class ArmTargetRequest(BaseModel):
    purpose: str = "Academic Continuous Assessment"
    accept_waitlist: bool = False
    user_permitted_automation: bool = True
    booking_mode: str = "AUTO_BOOK"

class PreflightCheckItem(BaseModel):
    name: str
    passed: bool
    critical: bool = True
    detail: str

class PreflightResponse(BaseModel):
    target_id: Optional[int] = None
    target_title: str
    target_room: Optional[str] = None
    target_date: Optional[str] = None
    target_time: Optional[str] = None
    passed: bool
    timestamp: str
    checks: List[PreflightCheckItem]
    summary: str

class BookingAttemptResponse(BaseModel):
    id: int
    user_id: Optional[int] = 1
    preference_id: Optional[int] = None
    target_event_id: Optional[str] = None
    session_id: Optional[str] = None
    mode: str = "AUTO_BOOK"
    purpose: Optional[str] = None
    status: str
    verified: bool = False
    retry_count: Optional[int] = 0
    response_message: Optional[str] = None
    attempted_at: Optional[str] = None
    execution_duration_ms: Optional[int] = None

class UserRegisterRequest(BaseModel):
    username: str
    password: str

class UserLoginRequest(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    created_at: Optional[str] = None

class AuthResponse(BaseModel):
    success: bool
    token: str
    user: UserResponse
