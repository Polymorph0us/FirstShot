import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.models.user import User, UserSession

SESSION_DURATION_DAYS = 14

def hash_password(password: str) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with random salt."""
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
    return f"{salt}:{key.hex()}"

def verify_password(password: str, stored_hash: str) -> bool:
    """Verify password against stored salt:key hash."""
    try:
        salt, key_hex = stored_hash.split(":")
        key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
        return hmac.compare_digest(key.hex(), key_hex)
    except Exception:
        return False

def generate_session_token() -> str:
    return secrets.token_hex(32)

async def create_user_session(db: AsyncSession, user_id: int) -> str:
    token = generate_session_token()
    expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_DURATION_DAYS)
    session = UserSession(
        session_token=token,
        user_id=user_id,
        expires_at=expires_at
    )
    db.add(session)
    await db.commit()
    return token

async def get_user_from_token(token: str, db: AsyncSession) -> Optional[User]:
    """Retrieve active user for a valid, non-expired session token."""
    if not token:
        return None
    now = datetime.now(timezone.utc)
    res = await db.execute(
        select(UserSession).where(
            UserSession.session_token == token,
            UserSession.expires_at > now
        )
    )
    user_session = res.scalars().first()
    if not user_session:
        return None
    return await db.get(User, user_session.user_id)

async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Authenticate request via Bearer token or HttpOnly cookie.
    Strictly raises 401 Unauthorized for unauthenticated requests.
    Never defaults to an anonymous or owner identity.
    """
    token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()

    if not token:
        token = request.cookies.get("fs_session")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in to FirstShot."
        )

    user = await get_user_from_token(token, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid. Please log in again."
        )

    return user
