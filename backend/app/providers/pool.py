import asyncio
import os
from pathlib import Path
from typing import Dict

from app.core.config import settings
from app.models.user import User
from app.providers.base import BaseProvider
from app.providers.saveetha import SaveethaProvider


class ProviderPool:
    """
    Manages isolated, per-user SaveethaProvider instances.
    Each user gets a dedicated Chromium profile directory and mutex lock.
    """
    def __init__(self):
        self._providers: Dict[int, BaseProvider] = {}
        self._locks: Dict[int, asyncio.Lock] = {}
        self._pool_lock = asyncio.Lock()

    def get_profile_dir_for_user(self, user: User) -> str:
        if user.role == "owner" or user.id == 1:
            return settings.SAVEETHA_PROFILE_DIR
        user_dir = Path(settings.PROFILES_BASE_DIR) / f"user_{user.id}"
        os.makedirs(user_dir, exist_ok=True)
        return str(user_dir)

    async def get_provider(self, user: User, provider_cls=SaveethaProvider) -> BaseProvider:
        async with self._pool_lock:
            if user.id not in self._locks:
                self._locks[user.id] = asyncio.Lock()

            if user.id in self._providers:
                return self._providers[user.id]

            profile_dir = self.get_profile_dir_for_user(user)
            provider = provider_cls(profile_dir=profile_dir)
            self._providers[user.id] = provider
            return provider

    def get_lock(self, user_id: int) -> asyncio.Lock:
        if user_id not in self._locks:
            self._locks[user_id] = asyncio.Lock()
        return self._locks[user_id]

    async def close_user_provider(self, user_id: int):
        async with self._pool_lock:
            provider = self._providers.pop(user_id, None)
            if provider:
                await provider.close()

    async def close_all(self):
        async with self._pool_lock:
            for p in self._providers.values():
                try:
                    await p.close()
                except Exception:
                    pass
            self._providers.clear()

provider_pool = ProviderPool()
