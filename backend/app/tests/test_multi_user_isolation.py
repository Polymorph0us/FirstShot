import os
import shutil
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.auth import get_current_user
from app.core.config import settings
from app.database.session import AsyncSessionLocal, init_db
from app.main import app
from app.models.booking_attempt import BookingAttempt
from app.models.user import User
from app.providers.pool import provider_pool


@pytest.fixture(autouse=True)
def remove_auth_override():
    """Ensure tests in this module run against REAL authentication without dependency override."""
    app.dependency_overrides.pop(get_current_user, None)
    yield
    app.dependency_overrides.pop(get_current_user, None)

@pytest.fixture(scope="module", autouse=True)
def cleanup_user_profiles():
    yield
    # Cleanup test profiles dir
    test_profiles = Path(settings.PROFILES_BASE_DIR)
    if test_profiles.exists():
        try:
            shutil.rmtree(test_profiles)
        except Exception:
            pass

@pytest.mark.asyncio
async def test_unauthenticated_requests_rejected():
    """Verify that unauthenticated requests strictly return 401 Unauthorized across protected endpoints."""
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Preferences
        res = await client.get("/api/preferences/")
        assert res.status_code == 401
        assert "Authentication required" in res.json()["detail"]

        # Booking attempts
        res = await client.get("/api/booking/attempts")
        assert res.status_code == 401

        # Session status
        res = await client.get("/api/session/status")
        assert res.status_code == 401

        # Events
        res = await client.get("/api/events/")
        assert res.status_code == 401

@pytest.mark.asyncio
async def test_user_registration_and_login():
    """Verify registration, password verification, and independent session issuance for Alice and Bob."""
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register Alice
        res_alice = await client.post("/api/auth/register", json={
            "username": "alice",
            "password": "AliceSecretPassword123"
        })
        assert res_alice.status_code == 201
        alice_data = res_alice.json()
        assert alice_data["user"]["username"] == "alice"
        assert alice_data["user"]["role"] == "student"
        alice_token = alice_data["token"]
        assert len(alice_token) > 20

        # Register Bob
        res_bob = await client.post("/api/auth/register", json={
            "username": "bob",
            "password": "BobSecretPassword456"
        })
        assert res_bob.status_code == 201
        bob_data = res_bob.json()
        assert bob_data["user"]["username"] == "bob"
        bob_token = bob_data["token"]

        # Duplicate registration prevented
        res_dup = await client.post("/api/auth/register", json={
            "username": "alice",
            "password": "AnotherPassword"
        })
        assert res_dup.status_code == 409

        # Login with invalid password
        res_bad_pw = await client.post("/api/auth/login", json={
            "username": "alice",
            "password": "WrongPassword"
        })
        assert res_bad_pw.status_code == 401

        # Login with correct password
        res_login = await client.post("/api/auth/login", json={
            "username": "alice",
            "password": "AliceSecretPassword123"
        })
        assert res_login.status_code == 200
        assert "token" in res_login.json()

        # Check /api/auth/me for Alice
        res_me_alice = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {alice_token}"}
        )
        assert res_me_alice.status_code == 200
        assert res_me_alice.json()["username"] == "alice"

        # Check /api/auth/me for Bob
        res_me_bob = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {bob_token}"}
        )
        assert res_me_bob.status_code == 200
        assert res_me_bob.json()["username"] == "bob"

@pytest.mark.asyncio
async def test_isolated_profile_directories():
    """Verify that Owner, Alice, and Bob receive isolated, non-overlapping Chromium profile paths."""
    await init_db()
    async with AsyncSessionLocal() as session:
        owner = await session.get(User, 1)
        res_alice = await session.execute(select(User).where(User.username == "alice"))
        alice = res_alice.scalars().first()
        res_bob = await session.execute(select(User).where(User.username == "bob"))
        bob = res_bob.scalars().first()

    assert owner is not None
    assert alice is not None
    assert bob is not None

    owner_profile = provider_pool.get_profile_dir_for_user(owner)
    alice_profile = provider_pool.get_profile_dir_for_user(alice)
    bob_profile = provider_pool.get_profile_dir_for_user(bob)

    # 1. Owner uses explicit personal profile
    assert owner_profile == settings.SAVEETHA_PROFILE_DIR
    assert "user_" not in owner_profile

    # 2. Alice uses isolated user directory
    assert f"user_{alice.id}" in alice_profile
    assert os.path.isabs(alice_profile) or str(alice_profile).startswith(".local")

    # 3. Bob uses distinct isolated user directory
    assert f"user_{bob.id}" in bob_profile

    # 4. Strictly non-overlapping
    assert owner_profile != alice_profile
    assert owner_profile != bob_profile
    assert alice_profile != bob_profile

@pytest.mark.asyncio
async def test_preference_and_target_data_isolation():
    """Verify that Alice and Bob can never see, modify, or delete each other's target slots."""
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Get Alice & Bob tokens
        alice_login = await client.post("/api/auth/login", json={"username": "alice", "password": "AliceSecretPassword123"})
        alice_token = alice_login.json()["token"]
        bob_login = await client.post("/api/auth/login", json={"username": "bob", "password": "BobSecretPassword456"})
        bob_token = bob_login.json()["token"]

        alice_headers = {"Authorization": f"Bearer {alice_token}"}
        bob_headers = {"Authorization": f"Bearer {bob_token}"}

        # Alice creates a target
        alice_target_res = await client.post("/api/preferences/", json={
            "title": "Alice Software Engineering Slot",
            "preferred_date": "2026-11-20",
            "preferred_time": "08:00",
            "preferred_room": "1731",
            "allow_waitlist": True
        }, headers=alice_headers)
        assert alice_target_res.status_code == 200
        alice_target = alice_target_res.json()
        alice_target_id = alice_target["id"]
        assert alice_target["user_id"] == alice_login.json()["user"]["id"]

        # Bob creates a target
        bob_target_res = await client.post("/api/preferences/", json={
            "title": "Bob Machine Learning Slot",
            "preferred_date": "2026-11-20",
            "preferred_time": "09:45",
            "preferred_room": "1851",
            "allow_waitlist": False
        }, headers=bob_headers)
        assert bob_target_res.status_code == 200
        bob_target = bob_target_res.json()
        bob_target_id = bob_target["id"]
        assert bob_target["user_id"] == bob_login.json()["user"]["id"]

        # Alice lists preferences -> sees ONLY Alice's target
        alice_list = await client.get("/api/preferences/", headers=alice_headers)
        assert alice_list.status_code == 200
        alice_prefs = alice_list.json()
        assert any(p["id"] == alice_target_id for p in alice_prefs)
        assert not any(p["id"] == bob_target_id for p in alice_prefs)

        # Bob lists preferences -> sees ONLY Bob's target
        bob_list = await client.get("/api/preferences/", headers=bob_headers)
        assert bob_list.status_code == 200
        bob_prefs = bob_list.json()
        assert any(p["id"] == bob_target_id for p in bob_prefs)
        assert not any(p["id"] == alice_target_id for p in bob_prefs)

        # Cross-user modification forbidden: Alice tries to update Bob's target -> 404
        update_res = await client.put(f"/api/preferences/{bob_target_id}", json={
            "preferred_room": "9999"
        }, headers=alice_headers)
        assert update_res.status_code == 404

        # Cross-user deletion forbidden: Alice tries to delete Bob's target -> 404
        del_res = await client.delete(f"/api/preferences/{bob_target_id}", headers=alice_headers)
        assert del_res.status_code == 404

        # Bob's target remains untouched
        bob_check = await client.get("/api/preferences/", headers=bob_headers)
        assert any(p["id"] == bob_target_id for p in bob_check.json())

@pytest.mark.asyncio
async def test_booking_attempt_isolation():
    """Verify that booking history is strictly isolated per tenant."""
    await init_db()
    async with AsyncSessionLocal() as session:
        res_alice = await session.execute(select(User).where(User.username == "alice"))
        alice = res_alice.scalars().first()
        res_bob = await session.execute(select(User).where(User.username == "bob"))
        bob = res_bob.scalars().first()

        # Insert attempt for Alice
        alice_attempt = BookingAttempt(
            user_id=alice.id,
            session_id="11111",
            mode="ASSIST",
            purpose="Alice Continuous Assessment",
            status="CONFIRMED",
            verified=True
        )
        session.add(alice_attempt)

        # Insert attempt for Bob
        bob_attempt = BookingAttempt(
            user_id=bob.id,
            session_id="22222",
            mode="AUTO_BOOK",
            purpose="Bob Autonomous Target",
            status="CONFIRMED",
            verified=True
        )
        session.add(bob_attempt)
        await session.commit()
        alice_att_id = alice_attempt.id
        bob_att_id = bob_attempt.id

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        alice_login = await client.post("/api/auth/login", json={"username": "alice", "password": "AliceSecretPassword123"})
        alice_token = alice_login.json()["token"]
        bob_login = await client.post("/api/auth/login", json={"username": "bob", "password": "BobSecretPassword456"})
        bob_token = bob_login.json()["token"]

        # Alice queries attempts
        alice_res = await client.get("/api/booking/attempts", headers={"Authorization": f"Bearer {alice_token}"})
        assert alice_res.status_code == 200
        alice_attempts = alice_res.json()
        assert any(a["id"] == alice_att_id for a in alice_attempts)
        assert not any(a["id"] == bob_att_id for a in alice_attempts)

        # Bob queries attempts
        bob_res = await client.get("/api/booking/attempts", headers={"Authorization": f"Bearer {bob_token}"})
        assert bob_res.status_code == 200
        bob_attempts = bob_res.json()
        assert any(a["id"] == bob_att_id for a in bob_attempts)
        assert not any(a["id"] == alice_att_id for a in bob_attempts)

@pytest.mark.asyncio
async def test_simultaneous_locks_and_concurrency():
    """Verify that per-user locks allow Alice and Bob to execute operations concurrently without blocking."""
    await init_db()
    async with AsyncSessionLocal() as session:
        res_alice = await session.execute(select(User).where(User.username == "alice"))
        alice = res_alice.scalars().first()
        res_bob = await session.execute(select(User).where(User.username == "bob"))
        bob = res_bob.scalars().first()

    alice_lock = provider_pool.get_lock(alice.id)
    bob_lock = provider_pool.get_lock(bob.id)

    # Acquire Alice lock
    await alice_lock.acquire()
    assert alice_lock.locked() is True

    # Bob's lock MUST remain unlocked and acquirable immediately
    assert bob_lock.locked() is False
    await bob_lock.acquire()
    assert bob_lock.locked() is True

    # Release both
    alice_lock.release()
    bob_lock.release()
    assert alice_lock.locked() is False
    assert bob_lock.locked() is False

@pytest.mark.asyncio
async def test_logout_and_session_invalidation():
    """Verify that logging out revokes only that user's session token."""
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        alice_login = await client.post("/api/auth/login", json={"username": "alice", "password": "AliceSecretPassword123"})
        alice_token = alice_login.json()["token"]
        bob_login = await client.post("/api/auth/login", json={"username": "bob", "password": "BobSecretPassword456"})
        bob_token = bob_login.json()["token"]

        # Alice logs out
        logout_res = await client.post("/api/auth/logout", headers={"Authorization": f"Bearer {alice_token}"})
        assert logout_res.status_code == 200

        # Alice's token is now revoked
        me_res = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {alice_token}"})
        assert me_res.status_code == 401

        # Bob's session remains fully active
        bob_me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {bob_token}"})
        assert bob_me.status_code == 200
        assert bob_me.json()["username"] == "bob"
