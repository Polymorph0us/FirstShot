import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from playwright.async_api import async_playwright
from sqlalchemy import select

from app.core.auth import get_current_user
from app.core.config import settings
from app.database.session import AsyncSessionLocal
from app.models.schemas import SessionStatusResponse
from app.models.user import User, UserSession
from app.providers.pool import provider_pool

router = APIRouter(prefix="/api/session", tags=["Session"])

@router.get("/status", response_model=SessionStatusResponse)
async def get_session_status(current_user: User = Depends(get_current_user)):
    """Check whether the authenticated user's isolated browser profile has an active Saveetha session."""
    provider = await provider_pool.get_provider(current_user)
    status_data = await provider.check_session()
    return SessionStatusResponse(
        authenticated=status_data.get("authenticated", False),
        profile_dir=provider.profile_dir,
        portal_url=provider.event_url,
        message=status_data.get("message", "Unknown status")
    )

@router.post("/reauthenticate")
async def trigger_reauthenticate(current_user: User = Depends(get_current_user)):
    """
    Launch isolated visible browser on host screen.
    Only permitted for the local owner user. Remote students use the remote-auth stream.
    """
    if current_user.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local desktop display launch is only permitted for the workstation owner. Please use the remote in-browser interactive login."
        )

    provider = await provider_pool.get_provider(current_user)
    success = await provider.reauthenticate()
    return {
        "success": success,
        "message": "Reauthentication completed." if success else "Reauthentication timed out or cancelled."
    }

@router.websocket("/remote-auth")
async def remote_auth_screencast(websocket: WebSocket, token: str = Query(...)):
    """
    Privileged interactive remote browser streaming via Playwright CDP.
    Streams headless browser frames to the authenticated student's remote canvas
    and forwards input events directly to the isolated Chromium session.
    """
    await websocket.accept()

    # 1. Authenticate user from session token
    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
        res = await db.execute(
            select(UserSession).where(
                UserSession.session_token == token,
                UserSession.expires_at > now
            )
        )
        user_sess = res.scalars().first()
        if not user_sess:
            await websocket.send_json({"type": "error", "message": "Invalid or expired session token."})
            await websocket.close(code=1008)
            return

        user = await db.get(User, user_sess.user_id)
        if not user:
            await websocket.close(code=1008)
            return

    # 2. Acquire user provider lock to prevent concurrent profile access
    lock = provider_pool.get_lock(user.id)
    if lock.locked():
        await websocket.send_json({"type": "error", "message": "Another browser operation is currently in progress for your account."})
        await websocket.close()
        return

    async with lock:
        # Close any headless provider instance before opening interactive session
        await provider_pool.close_user_provider(user.id)
        profile_dir = provider_pool.get_profile_dir_for_user(user)

        p = await async_playwright().start()
        context = await p.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=True,  # 100% headless, zero window on host!
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled"
            ],
            viewport={"width": 1024, "height": 768}
        )
        page = context.pages[0] if context.pages else await context.new_page()

        try:
            cdp = await page.context.new_cdp_session(page)
            screencast_active = True

            async def on_screencast_frame(event):
                nonlocal screencast_active
                if not screencast_active:
                    return
                try:
                    await websocket.send_json({
                        "type": "frame",
                        "data": event["data"],
                        "metadata": event.get("metadata", {})
                    })
                    await cdp.send("Page.screencastFrameAck", {"sessionId": event["sessionId"]})
                except Exception:
                    screencast_active = False

            cdp.on("Page.screencastFrame", on_screencast_frame)

            await cdp.send("Page.startScreencast", {
                "format": "jpeg",
                "quality": 75,
                "maxWidth": 1024,
                "maxHeight": 768
            })

            # Navigate to Saveetha login URL
            await page.goto(settings.SAVEETHA_EVENT_URL, timeout=30000)

            # Receive client input events in background loop
            while True:
                # Check if page has completed login
                cur_url = page.url
                if "academicevents/event-booking" in cur_url and "login" not in cur_url:
                    await websocket.send_json({
                        "type": "authenticated",
                        "message": "Authentication successful! Your portal session has been saved."
                    })
                    await asyncio.sleep(1.0)
                    break

                try:
                    msg = await asyncio.wait_for(websocket.receive_json(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                except WebSocketDisconnect:
                    break

                mtype = msg.get("type")
                if mtype == "mouse":
                    action = msg.get("action")  # "mousePressed", "mouseReleased", "mouseMoved"
                    x = int(msg.get("x", 0))
                    y = int(msg.get("y", 0))
                    button = msg.get("button", "left")
                    click_count = msg.get("clickCount", 1)
                    await cdp.send("Input.dispatchMouseEvent", {
                        "type": action,
                        "x": x,
                        "y": y,
                        "button": button,
                        "clickCount": click_count
                    })
                elif mtype == "key":
                    action = msg.get("action")  # "keyDown", "keyUp", "rawKeyDown", "char"
                    key = msg.get("key", "")
                    text = msg.get("text", "")
                    code = msg.get("code", "")
                    params = {"type": action}
                    if text:
                        params["text"] = text
                    if key:
                        params["key"] = key
                    if code:
                        params["code"] = code
                    await cdp.send("Input.dispatchKeyEvent", params)
                elif mtype == "close":
                    break

        except Exception as e:
            try:
                await websocket.send_json({"type": "error", "message": f"Remote session error: {str(e)}"})
            except Exception:
                pass
        finally:
            screencast_active = False
            try:
                await cdp.send("Page.stopScreencast")
            except Exception:
                pass
            try:
                await context.close()
            except Exception:
                pass
            try:
                await p.stop()
            except Exception:
                pass
