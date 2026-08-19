"""Tests for ConfigSyncManager — bump, subscribe, notify event flow."""
import asyncio
import pytest

from app.services.config_sync_manager import ConfigSyncManager, get_config_sync_manager


class TestConfigSyncManager:
    """Integration-style tests for config sync event flow."""

    def setup_method(self):
        self.mgr = ConfigSyncManager()

    @pytest.mark.asyncio
    async def test_bump_version_increments(self):
        """Bumping a version always increases it."""
        user_id = 999001
        v0 = await self.mgr.get_version(user_id)
        v1 = await self.mgr.bump_version(user_id)
        assert v1 == v0 + 1
        v2 = await self.mgr.bump_version(user_id)
        assert v2 == v1 + 1

    @pytest.mark.asyncio
    async def test_persisted_version_is_idempotent_and_notified_once(self):
        user_id = 999005
        queue = await self.mgr.subscribe(user_id)

        first = await self.mgr.bump_version(user_id, persisted_version=8123)
        second = await self.mgr.bump_version(user_id, persisted_version=8123)

        assert first == 8123
        assert second == 8123
        event = await asyncio.wait_for(queue.get(), timeout=0.5)
        assert event["version"] == 8123
        assert queue.empty()

    @pytest.mark.asyncio
    async def test_subscribe_receives_bump_event(self):
        """A subscriber queue receives the new version when bump is called."""
        user_id = 999002
        q = await self.mgr.subscribe(user_id)
        await self.mgr.bump_version(user_id)

        # Should receive event within 0.5s
        try:
            event = await asyncio.wait_for(q.get(), timeout=0.5)
        except asyncio.TimeoutError:
            pytest.fail("订阅者在 0.5s 内未收到 bump 事件")
        assert event is not None
        assert "version" in event or "new_version" in event

    @pytest.mark.asyncio
    async def test_unsubscribe_no_event(self):
        """After unsubscribe, no event arrives."""
        user_id = 999003
        q = await self.mgr.subscribe(user_id)
        await self.mgr.unsubscribe(user_id, q)
        await self.mgr.bump_version(user_id)

        # queue should be empty
        assert q.empty()

    def test_get_config_sync_manager__singleton(self):
        """get_config_sync_manager returns the same instance."""
        m1 = get_config_sync_manager()
        m2 = get_config_sync_manager()
        assert m1 is m2

    @pytest.mark.asyncio
    async def test_get_all_versions(self):
        """get_all_versions returns a dict of user_id → version."""
        await self.mgr.bump_version(999004)
        versions = await self.mgr.get_all_versions()
        assert isinstance(versions, dict)
        assert 999004 in versions
        assert versions[999004] >= 1
