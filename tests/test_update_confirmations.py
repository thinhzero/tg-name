import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import bot_updater
from bot_updater import UpdatePlan, UpdateResult, UpdateRequests, run_update_check, run_update_action


class UpdateConfirmationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.requests = UpdateRequests()
        patcher = patch.object(bot_updater, "update_requests", self.requests)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.plan = UpdatePlan("a" * 40, "b" * 40, ahead=4)
        self.updater = SimpleNamespace(check=AsyncMock(return_value=self.plan), update=AsyncMock(return_value=UpdateResult(self.plan.current, self.plan.latest, updated=True, snapshot="snapshots/test")), request_restart=Mock())
        self.edit = AsyncMock()

    async def offer(self, userbot=False):
        await run_update_check(self.edit, updater=self.updater, owner_id=42, userbot=userbot)
        return self.requests.pending[(42, userbot)][0]

    async def test_check_only_reports_count_and_yes_no_controls(self):
        await self.offer()
        self.updater.check.assert_awaited_once()
        self.updater.update.assert_not_awaited()
        self.updater.request_restart.assert_not_called()
        self.assertIn("4 commit", self.edit.call_args.args[0])
        data = [button["callback_data"] for row in self.edit.call_args.kwargs["buttons"] for button in row]
        self.assertTrue(any(value.startswith("update_confirm:") for value in data))
        self.assertTrue(any(value.startswith("update_cancel:") for value in data))

    async def test_no_never_applies_or_restarts(self):
        token = await self.offer()
        await run_update_action(self.edit, 42, token, updater=self.updater, confirm=False)
        self.updater.update.assert_not_awaited()
        self.updater.request_restart.assert_not_called()
        self.assertIn("không cập nhật", self.edit.call_args.args[0])
        self.assertFalse(self.requests.pending)

    async def test_yes_applies_exact_plan_once_and_shows_snapshot(self):
        token = await self.offer()
        await run_update_action(self.edit, 42, token, updater=self.updater, secret_values=["private-key"])
        self.updater.update.assert_awaited_once()
        self.assertEqual(self.updater.update.call_args.kwargs["plan"], self.plan)
        self.assertEqual(self.updater.update.call_args.kwargs["secret_values"], ["private-key"])
        self.assertIn("snapshots/test", self.edit.call_args.args[0])
        self.updater.request_restart.assert_called_once()
        await run_update_action(self.edit, 42, token, updater=self.updater)
        self.updater.update.assert_awaited_once()

    async def test_other_owner_or_transport_cannot_confirm(self):
        token = await self.offer()
        await run_update_action(self.edit, 99, token, updater=self.updater)
        await run_update_action(self.edit, 42, token, updater=self.updater, userbot=True)
        self.updater.update.assert_not_awaited()
        self.assertIn((42, False), self.requests.pending)

    async def test_confirmation_expires_and_new_check_invalidates_old_token(self):
        with patch.object(bot_updater.time, "monotonic", return_value=100):
            token = await self.offer()
        with patch.object(bot_updater.time, "monotonic", return_value=401):
            await run_update_action(self.edit, 42, token, updater=self.updater)
        self.updater.update.assert_not_awaited()
        old = await self.offer()
        current = await self.offer()
        self.assertNotEqual(old, current)
        await run_update_action(self.edit, 42, old, updater=self.updater)
        self.updater.update.assert_not_awaited()

    async def test_home_invalidation_prevents_confirming_old_buttons(self):
        token = await self.offer()
        self.requests.cancel(42)
        await run_update_action(self.edit, 42, token, updater=self.updater)
        self.updater.update.assert_not_awaited()

    async def test_invalid_unicode_token_is_rejected_without_consuming_real_request(self):
        await self.offer()
        await run_update_action(self.edit, 42, "mã không hợp lệ", updater=self.updater)
        self.updater.update.assert_not_awaited()
        self.assertIn((42, False), self.requests.pending)

    async def test_userbot_offers_text_commands_not_inline_buttons(self):
        token = await self.offer(userbot=True)
        self.assertNotIn("buttons", self.edit.call_args.kwargs)
        self.assertIn(".updateconfirm " + token, self.edit.call_args.args[0])
        self.assertIn(".updatecancel " + token, self.edit.call_args.args[0])

    async def test_latest_or_diverged_never_offers_apply(self):
        for plan in (UpdatePlan("same", "same"), UpdatePlan("local", "remote", ahead=2, local_ahead=1)):
            self.updater.check.return_value = plan
            await run_update_check(self.edit, updater=self.updater, owner_id=42)
            self.assertFalse(self.requests.pending)
            self.assertNotIn("buttons", self.edit.call_args.kwargs)
        self.updater.update.assert_not_awaited()

    async def test_restart_still_happens_if_success_notification_fails(self):
        token = await self.offer()
        self.edit.side_effect = RuntimeError("offline")
        with self.assertRaises(RuntimeError):
            await run_update_action(self.edit, 42, token, updater=self.updater)
        self.updater.request_restart.assert_called_once()


if __name__ == "__main__":
    unittest.main()
