"""Video upload (resumable X-Goog-Upload protocol) support tests."""
import unittest

import httpx

from src.services.flow_client import FlowClient


MP4_BYTES = b"\x00\x00\x00\x18ftypisom" + b"0" * 32


def _handler_recording(calls, start_response=None, finalize_response=None):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.headers.get("X-Goog-Upload-Command") == "start":
            return start_response or httpx.Response(
                200,
                headers={
                    "X-Goog-Upload-Status": "active",
                    "X-Goog-Upload-URL": "https://uploads.example/session?upload_id=test-session",
                },
            )
        return finalize_response or httpx.Response(
            200,
            json={"mediaId": "uuid-1"},
            headers={"X-Goog-Upload-Status": "final"},
        )

    return handler


class FlowClientUploadVideoTests(unittest.IsolatedAsyncioTestCase):
    async def test_upload_video_start_then_finalize(self):
        calls = []
        transport = httpx.MockTransport(_handler_recording(calls))
        client = FlowClient(proxy_manager=None)

        media_id = await client.upload_video(
            access_token="at-x",
            project_id="proj-1",
            data=MP4_BYTES,
            transport=transport,
        )

        self.assertEqual(media_id, "uuid-1")
        self.assertEqual(len(calls), 2)

        start_req = calls[0]
        self.assertIn("aisandbox-pa.sandbox.googleapis.com", str(start_req.url))
        self.assertIn("/upload/v1/flow/upload/video/proj-1", str(start_req.url))
        self.assertIn("upload_protocol=resumable", str(start_req.url))
        self.assertEqual(start_req.headers["Authorization"], "Bearer at-x")
        self.assertEqual(
            start_req.headers["X-Goog-Upload-Content-Length"], str(len(MP4_BYTES))
        )
        self.assertEqual(start_req.headers["X-Goog-Upload-Content-Type"], "video/mp4")

        fin_req = calls[1]
        self.assertEqual(fin_req.headers["X-Goog-Upload-Command"], "upload, finalize")
        self.assertEqual(fin_req.headers["X-Goog-Upload-Offset"], "0")
        self.assertEqual(fin_req.content, MP4_BYTES)

    async def test_upload_video_start_http_error(self):
        calls = []
        transport = httpx.MockTransport(
            _handler_recording(
                calls, start_response=httpx.Response(401, text="Unauthorized")
            )
        )
        client = FlowClient(proxy_manager=None)

        with self.assertRaises(Exception) as ctx:
            await client.upload_video(
                access_token="bad-at",
                project_id="proj-1",
                data=MP4_BYTES,
                transport=transport,
            )
        self.assertIn("401", str(ctx.exception))
        self.assertEqual(len(calls), 1)

    async def test_upload_video_finalize_http_error(self):
        calls = []
        transport = httpx.MockTransport(
            _handler_recording(
                calls, finalize_response=httpx.Response(500, text="boom")
            )
        )
        client = FlowClient(proxy_manager=None)

        with self.assertRaises(Exception) as ctx:
            await client.upload_video(
                access_token="at-x",
                project_id="proj-1",
                data=MP4_BYTES,
                transport=transport,
            )
        self.assertIn("500", str(ctx.exception))

    async def test_upload_video_falls_back_to_media_name(self):
        calls = []
        transport = httpx.MockTransport(
            _handler_recording(
                calls,
                finalize_response=httpx.Response(
                    200,
                    json={"media": {"name": "uuid-2"}},
                    headers={"X-Goog-Upload-Status": "final"},
                ),
            )
        )
        client = FlowClient(proxy_manager=None)

        media_id = await client.upload_video(
            access_token="at-x",
            project_id="proj-1",
            data=MP4_BYTES,
            transport=transport,
        )
        self.assertEqual(media_id, "uuid-2")

    async def test_upload_video_missing_upload_url(self):
        calls = []
        transport = httpx.MockTransport(
            _handler_recording(
                calls,
                start_response=httpx.Response(
                    200, headers={"X-Goog-Upload-Status": "active"}
                ),
            )
        )
        client = FlowClient(proxy_manager=None)

        with self.assertRaises(Exception) as ctx:
            await client.upload_video(
                access_token="at-x",
                project_id="proj-1",
                data=MP4_BYTES,
                transport=transport,
            )
        self.assertIn("X-Goog-Upload-URL", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()


# ================= Task 2: /v1/videos/uploads 端点 + 归属登记 =================

import base64
from unittest.mock import AsyncMock, MagicMock

from src.api.routes import _parse_video_upload_request


def _data_url(mime: str = "video/mp4", data: bytes = MP4_BYTES) -> str:
    return f"data:{mime};base64," + base64.b64encode(data).decode()


class ParseVideoUploadRequestTests(unittest.TestCase):
    def test_data_url_decodes_bytes_and_mime(self):
        data, mime = _parse_video_upload_request(video=_data_url(), video_url=None)
        self.assertEqual(data, MP4_BYTES)
        self.assertEqual(mime, "video/mp4")

    def test_both_sources_rejected(self):
        with self.assertRaises(ValueError):
            _parse_video_upload_request(
                video=_data_url(), video_url="https://example.com/a.mp4"
            )

    def test_neither_source_rejected(self):
        with self.assertRaises(ValueError):
            _parse_video_upload_request(video=None, video_url=None)

    def test_invalid_base64_rejected(self):
        with self.assertRaises(ValueError):
            _parse_video_upload_request(
                video="data:video/mp4;base64,!!!not-base64!!!", video_url=None
            )

    def test_disallowed_mime_rejected(self):
        with self.assertRaises(ValueError):
            _parse_video_upload_request(video=_data_url(mime="image/png"), video_url=None)

    def test_oversize_rejected(self):
        big = b"0" * (50 * 1024 * 1024 + 1)
        with self.assertRaises(ValueError):
            _parse_video_upload_request(video=_data_url(data=big), video_url=None)

    def test_url_passthrough(self):
        data, mime = _parse_video_upload_request(
            video=None, video_url="https://example.com/a.mp4"
        )
        self.assertIsNone(data)
        self.assertIsNone(mime)


class UploadVideoOrchestrationTests(unittest.IsolatedAsyncioTestCase):
    def _make_handler(self):
        from src.services.generation_handler import GenerationHandler

        flow_client = MagicMock()
        flow_client.upload_video = AsyncMock(return_value="media-uuid-1")
        token_manager = MagicMock()
        token_manager.ensure_project_exists = AsyncMock(return_value="proj-9")
        load_balancer = MagicMock()
        token = MagicMock()
        token.id = 7
        token.at = "at-secret"
        load_balancer.select_token = AsyncMock(return_value=token)
        db = MagicMock()
        db.create_task = AsyncMock(return_value=1)
        db.update_task = AsyncMock()
        handler = GenerationHandler(
            flow_client=flow_client,
            token_manager=token_manager,
            load_balancer=load_balancer,
            db=db,
            concurrency_manager=MagicMock(),
            proxy_manager=None,
        )
        return handler, flow_client, token_manager, load_balancer, db

    async def test_upload_registers_ownership_for_uploading_token(self):
        handler, flow_client, token_manager, load_balancer, db = self._make_handler()

        media_id = await handler.upload_video_for_edit(MP4_BYTES, "video/mp4")

        self.assertEqual(media_id, "media-uuid-1")
        flow_client.upload_video.assert_awaited_once()
        kwargs = flow_client.upload_video.await_args.kwargs
        self.assertEqual(kwargs["access_token"], "at-secret")
        self.assertEqual(kwargs["project_id"], "proj-9")
        self.assertEqual(kwargs["data"], MP4_BYTES)
        self.assertEqual(kwargs["content_type"], "video/mp4")

        db.create_task.assert_awaited_once()
        created = db.create_task.await_args.args[0]
        self.assertEqual(created.token_id, 7)
        db.update_task.assert_awaited_once()
        update_args = db.update_task.await_args
        self.assertEqual(update_args.kwargs.get("media_generation_id"), "media-uuid-1")

    async def test_upload_without_available_token_raises_capacity_message(self):
        handler, flow_client, _, load_balancer, db = self._make_handler()
        load_balancer.select_token = AsyncMock(return_value=None)

        with self.assertRaises(Exception) as ctx:
            await handler.upload_video_for_edit(MP4_BYTES, "video/mp4")

        self.assertIn("没有可用的Token", str(ctx.exception))
        flow_client.upload_video.assert_not_awaited()
        db.create_task.assert_not_awaited()
