import asyncio
import importlib.util
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch


HAS_HTTP = importlib.util.find_spec("aiohttp") is not None
if HAS_HTTP:
    import file_transfer
    from file_transfer import FileTransfers, TransferProgress, guess_filename, link_argument, readable_size, safe_filename


@unittest.skipUnless(HAS_HTTP, "Cài aiohttp để kiểm thử tải/gửi file")
class FileTransferTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tg-name-file-tests-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runner = FileTransfers(max_size=20, timeout=1)
        self.addAsyncCleanup(self.runner.close)
        self.edit, self.upload = AsyncMock(), AsyncMock()
        self.parts, self.length = [b"hello", b" world"], None
        self.headers = {"Content-Disposition": 'attachment; filename="file.txt"'}
        self.started = asyncio.Event()
        self.block = False
        self.status = 200
        self.response_exited = False
        self.seen_paths = []
        original_temporary = tempfile.TemporaryDirectory

        def temporary(**kwargs):
            return original_temporary(dir=self.root, **kwargs)

        async def chunks(size):
            for part in self.parts:
                self.started.set()
                yield part
            if self.block:
                await asyncio.Event().wait()

        @asynccontextmanager
        async def response():
            try:
                yield SimpleNamespace(status=self.status, content_length=self.length, headers=self.headers, url="https://example.com/path/file.txt", content=SimpleNamespace(iter_chunked=chunks))
            finally:
                self.response_exited = True

        self.session = SimpleNamespace(get=Mock(side_effect=lambda *args, **kwargs: response()))

        @asynccontextmanager
        async def session_factory(**kwargs):
            yield self.session

        for patcher in (
            patch.object(file_transfer, "public_session", session_factory),
            patch.object(file_transfer.tempfile, "TemporaryDirectory", side_effect=temporary),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

        async def upload(path, filename, progress):
            self.seen_paths.append(path)
            self.assertTrue(path.is_file())
            self.assertEqual(path.read_bytes(), b"".join(self.parts))
            await progress(path.stat().st_size, path.stat().st_size)
        self.upload.side_effect = upload

    async def run_transfer(self, **kwargs):
        return await self.runner.run(
            "https://example.com/file?token=do-not-echo", self.edit, self.upload,
            **{"owner_id": 42, "chat_id": 42, "userbot": False, **kwargs},
        )

    def assert_clean(self):
        self.assertEqual(list(self.root.glob("tg-name-transfer-*")), [])
        self.assertIsNone(self.runner.job)

    async def test_success_streams_uploads_and_removes_only_its_temporary_directory(self):
        sentinel = self.root / ".env"
        sentinel.write_text("keep existing configuration")
        self.assertTrue(await self.run_transfer())
        self.upload.assert_awaited_once()
        self.assertEqual(self.upload.call_args.args[1], "file.txt")
        self.assertTrue(self.response_exited)
        self.assertFalse(self.seen_paths[0].exists())
        self.assertEqual(sentinel.read_text(), "keep existing configuration")
        self.assertIn("Đã gửi", self.edit.call_args.args[0])
        self.assertNotIn("do-not-echo", str(self.edit.call_args_list))
        self.assert_clean()

    async def test_declared_and_chunked_size_limits_stop_before_upload(self):
        for length in (1000, None):
            self.length, self.parts = length, [b"x" * 12, b"x" * 12]
            self.assertFalse(await self.run_transfer())
            self.assertIn("vượt giới hạn", self.edit.call_args.args[0])
            self.assert_clean()
        self.upload.assert_not_awaited()

    async def test_empty_download_is_not_uploaded(self):
        self.parts = []
        self.assertFalse(await self.run_transfer())
        self.upload.assert_not_awaited()
        self.assertIn("rỗng", self.edit.call_args.args[0])
        self.assert_clean()

    async def test_status_edit_failure_does_not_fail_a_successful_upload(self):
        self.edit.side_effect = RuntimeError("message deleted")
        self.assertTrue(await self.run_transfer())
        self.upload.assert_awaited_once()
        self.assert_clean()

    async def test_remote_filename_cannot_escape_temporary_directory(self):
        sentinel = self.root / "keep.txt"
        sentinel.write_text("keep")
        self.headers = {"Content-Disposition": 'attachment; filename="../../keep.txt"'}
        self.assertTrue(await self.run_transfer())
        self.assertEqual(self.seen_paths[0].name, "keep.txt")
        self.assertNotEqual(self.seen_paths[0].parent, self.root)
        self.assertEqual(sentinel.read_text(), "keep")
        self.assert_clean()

    async def test_http_or_upload_failure_does_not_leak_private_error_and_cleans_files(self):
        self.upload.side_effect = RuntimeError("private-token https://example.com/signed-url")
        self.assertFalse(await self.run_transfer())
        self.assertNotIn("private-token", str(self.edit.call_args_list))
        self.assert_clean()
        self.upload.reset_mock()
        self.status = 404
        self.assertFalse(await self.run_transfer())
        self.upload.assert_not_awaited()
        self.assert_clean()

    async def test_timeout_cancels_stream_and_cleans_partial_download(self):
        self.block = True
        self.runner.timeout = 0.02
        self.assertFalse(await self.run_transfer())
        self.assertTrue(self.response_exited)
        self.upload.assert_not_awaited()
        self.assertIn("quá 5 phút", self.edit.call_args.args[0])
        self.assert_clean()

    async def test_only_the_owner_in_the_same_chat_and_transport_can_cancel(self):
        self.block = True
        task = asyncio.create_task(self.run_transfer())
        await self.started.wait()
        self.assertFalse(self.runner.cancel(99, 42))
        self.assertFalse(self.runner.cancel(42, 99))
        self.assertFalse(self.runner.cancel(42, 42, userbot=True))
        self.assertTrue(self.runner.cancel(42, 42))
        self.assertFalse(await task)
        self.assertTrue(self.response_exited)
        self.assertIn("Đã hủy", self.edit.call_args.args[0])
        self.assert_clean()

    async def test_a_second_transfer_does_not_start_another_download(self):
        self.block = True
        first = asyncio.create_task(self.run_transfer())
        await self.started.wait()
        other_edit = AsyncMock()
        self.assertFalse(await self.runner.run("https://example.com/other", other_edit, self.upload, owner_id=99, chat_id=99))
        self.session.get.assert_called_once()
        self.assertIn("một tác vụ", other_edit.call_args.args[0])
        self.runner.cancel(42, 42)
        await first
        self.assert_clean()

    async def test_cancelling_during_upload_also_removes_the_downloaded_file(self):
        uploading = asyncio.Event()
        async def upload(path, filename, progress):
            self.assertTrue(path.is_file())
            uploading.set()
            await asyncio.Event().wait()
        self.upload.side_effect = upload
        task = asyncio.create_task(self.run_transfer())
        await uploading.wait()
        self.assertTrue(self.runner.cancel(42, 42))
        self.assertFalse(await task)
        self.assert_clean()

    async def test_shutdown_cancellation_propagates_and_waits_for_cleanup(self):
        self.block = True
        task = asyncio.create_task(self.run_transfer(userbot=True))
        await self.started.wait()
        await self.runner.close(userbot=False)
        self.assertFalse(task.done())
        await self.runner.close(userbot=True)
        self.assertTrue(task.cancelled())
        self.assertTrue(self.response_exited)
        self.assert_clean()

    async def test_bad_urls_and_missing_arguments_do_not_create_files_or_requests(self):
        for url in ("", "file:///etc/passwd", "http://localhost/file", "http://127.0.0.1/file", "https://user:password@example.com/file"):
            self.assertFalse(await self.runner.run(url, self.edit, self.upload, owner_id=42, chat_id=42))
            self.assert_clean()
        self.session.get.assert_not_called()
        self.upload.assert_not_awaited()


@unittest.skipUnless(HAS_HTTP, "Cài aiohttp để kiểm thử progress và tên file")
class TransferUtilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_safe_filenames_strip_paths_hidden_names_controls_and_limit_bytes(self):
        for name, expected in (("../../.env", "env"), (r"C:\path\file.zip", "file.zip"), ("...", "download.bin"), ("a\x00\u202eb.txt", "ab.txt"), ("a<b>.zip", "a_b_.zip")):
            self.assertEqual(safe_filename(name), expected)
        self.assertLessEqual(len(safe_filename("ấ" * 500).encode()), 180)
        self.assertEqual(guess_filename("https://example.com/path/file.zip?secret=hidden", {}), "file.zip")
        self.assertEqual(guess_filename("https://example.com/", {}), "download.bin")
        self.assertEqual(guess_filename("https://example.com/file", {"Content-Disposition": "attachment; filename*=UTF-8''t%C3%AAn.zip"}), "tên.zip")

    async def test_link_argument_accepts_explicit_or_replied_plain_link_only(self):
        event = SimpleNamespace(is_reply=True, get_reply_message=AsyncMock(return_value=SimpleNamespace(raw_text="tải https://example.com/file nhé")))
        self.assertEqual(await link_argument(event, " https://other.example/file "), "https://other.example/file")
        event.get_reply_message.assert_not_awaited()
        self.assertEqual(await link_argument(event, ""), "https://example.com/file")
        event.get_reply_message.side_effect = RuntimeError("message unavailable")
        self.assertEqual(await link_argument(event, ""), "")
        event.is_reply = False
        self.assertEqual(await link_argument(event, ""), "")

    async def test_progress_is_throttled_per_task_and_resets_when_upload_starts(self):
        edit = AsyncMock()
        first, second = TransferProgress(edit, "<file>"), TransferProgress(edit, "other")
        with patch.object(file_transfer.time, "monotonic", return_value=100):
            await first.update(10, 100)
            await first.update(20, 100)
            await second.update(1, 0)
        self.assertEqual(edit.await_count, 2)
        self.assertIn("&lt;file&gt;", edit.call_args_list[0].args[0])
        with patch.object(file_transfer.time, "monotonic", return_value=101):
            await first.update(0, 100, "upload")
        self.assertEqual(edit.await_count, 3)
        self.assertIn("Đang gửi Telegram", edit.call_args.args[0])
        with patch.object(file_transfer.time, "monotonic", return_value=104):
            await first.update(100, 100, "upload")
        self.assertIn("100.0%", edit.call_args.args[0])

    async def test_progress_errors_are_nonfatal_but_cancellation_propagates(self):
        edit = AsyncMock(side_effect=RuntimeError("edit unavailable"))
        progress = TransferProgress(edit, "file")
        await progress.update(1, 10)
        await progress.update(1, 10, "upload")
        edit.assert_awaited_once()
        with self.assertRaises(asyncio.CancelledError):
            await TransferProgress(AsyncMock(side_effect=asyncio.CancelledError()), "file").update(1, 10)

    async def test_sizes_use_binary_units_and_do_not_show_negative_values(self):
        self.assertEqual(readable_size(1024 * 1024), "1.0 MiB")
        self.assertEqual(readable_size(-1), "0.0 B")


if __name__ == "__main__":
    unittest.main()
