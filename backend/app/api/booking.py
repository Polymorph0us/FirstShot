from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.database.session import get_db
from app.models.booking_attempt import BookingAttempt
from app.models.schemas import (
    BookingAttemptResponse,
    ConfirmBookingRequest,
    ConfirmBookingResponse,
    PrepareBookingRequest,
    PrepareBookingResponse,
)
from app.models.user import User
from app.providers.pool import provider_pool

router = APIRouter(prefix="/api/booking", tags=["Booking"])

@router.post("/prepare", response_model=PrepareBookingResponse)
async def prepare_booking(
    req: PrepareBookingRequest,
    current_user: User = Depends(get_current_user)
):
    """
    ASSIST MODE (Step 1): Inspects the session, verifies availability, and prepares parameters.
    No booking is submitted here.
    """
    provider = await provider_pool.get_provider(current_user)

    # 1. Verify authenticated session in user's isolated profile
    sess_status = await provider.check_session()
    if not sess_status.get("authenticated"):
        raise HTTPException(
            status_code=401,
            detail="Saveetha portal session expired or not authenticated. Please log in first."
        )

    # 2. Retrieve & verify event availability
    result = await provider.prepare_booking(req.event_id, req.purpose)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message", "Could not prepare booking"))

    return PrepareBookingResponse(
        event_id=result["event_id"],
        session_id=str(result["session_id"]),
        title=result["title"],
        venue=result.get("venue"),
        date=result.get("date"),
        time=result.get("time"),
        booking_action=result["booking_action"],
        purpose=result["purpose"],
        ready_to_submit=result["ready_to_submit"],
        status=result["status"],
        message=result["message"]
    )

@router.post("/confirm", response_model=ConfirmBookingResponse)
async def confirm_booking(
    req: ConfirmBookingRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    ASSIST MODE (Step 2): Controlled booking confirmation.
    Requires explicit user confirmation before executing submission.
    Verifies server response and prevents duplicate submissions.
    """
    # 1. Explicit user confirmation requirement
    if not req.user_confirmed:
        raise HTTPException(
            status_code=400,
            detail="Explicit user confirmation is required. You must check 'I confirm this booking submission' before proceeding."
        )

    # 2. Purpose validation
    clean_purpose = req.purpose.strip() if req.purpose else ""
    if not clean_purpose:
        raise HTTPException(status_code=400, detail="Purpose field is required by the college portal.")
    if len(clean_purpose) > 255:
        raise HTTPException(status_code=400, detail="Purpose exceeds maximum length of 255 characters.")

    # 3. Check session authentication for this user
    provider = await provider_pool.get_provider(current_user)
    sess_status = await provider.check_session()
    if not sess_status.get("authenticated"):
        raise HTTPException(status_code=401, detail="Portal session expired. Please re-authenticate.")

    # 4. Submit booking with duplicate prevention and verification
    submit_result = await provider.submit_booking(
        session_id=req.session_id,
        purpose=clean_purpose,
        action=req.booking_action
    )

    # Record persistent booking attempt for this user
    status_str = "CONFIRMED" if submit_result.get("success") else submit_result.get("status", "FAILED")
    attempt = BookingAttempt(
        user_id=current_user.id,
        session_id=str(req.session_id),
        mode="ASSIST",
        purpose=clean_purpose,
        status=status_str,
        verified=submit_result.get("verified", False),
        response_message=submit_result.get("message", ""),
        attempted_at=datetime.now(timezone.utc)
    )
    db.add(attempt)
    await db.commit()

    if not submit_result.get("success") and submit_result.get("status") == "DUPLICATE_ATTEMPT_PREVENTED":
        raise HTTPException(status_code=409, detail=submit_result.get("message"))

    if not submit_result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=submit_result.get("message", "Booking submission failed or was rejected by portal.")
        )

    return ConfirmBookingResponse(
        success=submit_result["success"],
        event_id=req.event_id,
        session_id=req.session_id,
        title=submit_result.get("title", "Assessment Session"),
        booking_action=req.booking_action,
        status=submit_result.get("status", "CONFIRMED"),
        message=submit_result.get("message", "Booking confirmed."),
        verified=submit_result.get("verified", False),
        timestamp=submit_result.get("timestamp", datetime.now(timezone.utc).isoformat())
    )

@router.get("/attempts", response_model=List[BookingAttemptResponse])
async def list_booking_attempts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List persistent log of booking attempts scoped strictly to the authenticated user."""
    result = await db.execute(
        select(BookingAttempt)
        .where(BookingAttempt.user_id == current_user.id)
        .order_by(BookingAttempt.id.desc())
        .limit(50)
    )
    attempts = result.scalars().all()
    return [a.to_dict() for a in attempts]
