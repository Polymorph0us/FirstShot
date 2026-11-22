from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import create_user_session, get_current_user, hash_password, verify_password
from app.database.session import get_db
from app.models.schemas import AuthResponse, UserLoginRequest, UserRegisterRequest, UserResponse
from app.models.user import User, UserSession
from app.providers.pool import provider_pool

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register_user(data: UserRegisterRequest, response: Response, db: AsyncSession = Depends(get_db)):
    clean_username = data.username.strip().lower()
    if not clean_username or len(clean_username) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username must be at least 3 characters long."
        )
    if not data.password or len(data.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters long."
        )

    # Check existing username
    res = await db.execute(select(User).where(User.username == clean_username))
    if res.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username is already taken. Please choose another."
        )

    pwd_hash = hash_password(data.password)
    # Temporary placeholder directory, updated with id once inserted
    new_user = User(
        username=clean_username,
        password_hash=pwd_hash,
        role="student",
        profile_dir=""
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    # Scoped profile directory
    new_user.profile_dir = provider_pool.get_profile_dir_for_user(new_user)
    await db.commit()

    token = await create_user_session(db, new_user.id)
    response.set_cookie(
        key="fs_session",
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,  # Can be true over HTTPS
        max_age=14 * 86400
    )

    return AuthResponse(
        success=True,
        token=token,
        user=UserResponse(
            id=new_user.id,
            username=new_user.username,
            role=new_user.role,
            created_at=new_user.created_at.isoformat() if new_user.created_at else None
        )
    )

@router.post("/login", response_model=AuthResponse)
async def login_user(data: UserLoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    clean_username = data.username.strip().lower()
    res = await db.execute(select(User).where(User.username == clean_username))
    user = res.scalars().first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password."
        )

    token = await create_user_session(db, user.id)
    response.set_cookie(
        key="fs_session",
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=14 * 86400
    )

    return AuthResponse(
        success=True,
        token=token,
        user=UserResponse(
            id=user.id,
            username=user.username,
            role=user.role,
            created_at=user.created_at.isoformat() if user.created_at else None
        )
    )

@router.post("/logout")
async def logout_user(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Invalidate session in DB
    res = await db.execute(select(UserSession).where(UserSession.user_id == current_user.id))
    sessions = res.scalars().all()
    for s in sessions:
        await db.delete(s)
    await db.commit()

    # Close user's browser context if active
    await provider_pool.close_user_provider(current_user.id)

    response.delete_cookie(key="fs_session")
    return {"success": True, "message": "Successfully logged out."}

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        created_at=current_user.created_at.isoformat() if current_user.created_at else None
    )
