"""Video edit (abra_edit) support tests."""
import re

import pytest

from src.api.routes import (
    _extract_prompt_and_images_from_openai_messages,
    _parse_edit_directive,
)


def _async(value):
    async def _inner(*args, **kwargs):
        return value
    return _inner()


def test_parse_edit_directive_defaults():
    d = _parse_edit_directive("edit://abc-123")
    assert d == {"media_id": "abc-123", "start_frame": 0, "end_frame": 240}


def test_parse_edit_directive_frame_range():
    d = _parse_edit_directive("edit://abc-123?start_frame=30&end_frame=90")
    assert d == {"media_id": "abc-123", "start_frame": 30, "end_frame": 90}


def test_parse_edit_directive_rejects_empty_media_id():
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        _parse_edit_directive("edit://")


def test_parse_edit_directive_rejects_inverted_range():
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        _parse_edit_directive("edit://abc?start_frame=90&end_frame=30")


def test_parse_edit_directive_rejects_end_frame_above_300():
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        _parse_edit_directive("edit://abc?start_frame=0&end_frame=301")


def test_parse_edit_directive_rejects_non_integer_frames():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        _parse_edit_directive("edit://abc?start_frame=xyz")
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_extract_messages_recognizes_edit_prefix():
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "把背景墙上的画移除"},
                {"type": "image_url", "image_url": {"url": "edit://ae89d005-x?start_frame=0&end_frame=240"}},
            ],
        }
    ]
    # ChatMessage 为 pydantic 模型,按 routes.py 现有测试同款方式构造
    from src.api.routes import ChatMessage
    cmsgs = [ChatMessage(**m) for m in messages]
    prompt, images, video_media_id, edit_directive = (
        await _extract_prompt_and_images_from_openai_messages(cmsgs)
    )
    assert prompt == "把背景墙上的画移除"
    assert images == []
    assert video_media_id is None
    assert edit_directive == {
        "media_id": "ae89d005-x",
        "start_frame": 0,
        "end_frame": 240,
    }


@pytest.mark.asyncio
async def test_extract_messages_extend_still_works():
    from src.api.routes import ChatMessage
    cmsgs = [
        ChatMessage(
            role="user",
            content=[
                {"type": "text", "text": "续写"},
                {"type": "image_url", "image_url": {"url": "extend://m-1"}},
            ],
        )
    ]
    prompt, images, video_media_id, edit_directive = (
        await _extract_prompt_and_images_from_openai_messages(cmsgs)
    )
    assert video_media_id == "m-1"
    assert edit_directive is None


def test_edit_model_config_entries():
    from src.services.generation_handler import MODEL_CONFIG
    for name, ar in (("flow_edit", "VIDEO_ASPECT_RATIO_LANDSCAPE"),
                     ("flow_edit_portrait", "VIDEO_ASPECT_RATIO_PORTRAIT")):
        cfg = MODEL_CONFIG[name]
        assert cfg["type"] == "video"
        assert cfg["video_type"] == "edit"
        assert cfg["model_key"] == "abra_edit"
        assert cfg["aspect_ratio"] == ar
        assert cfg["requires_video_id"] is True
        assert cfg["supports_images"] is True
        assert cfg["min_images"] == 0
        assert cfg["max_images"] == 1
        assert cfg["use_v2_model_config"] is False


def test_edit_model_alias_resolution():
    import types

    from src.core.model_resolver import resolve_model_name
    from src.services.generation_handler import MODEL_CONFIG

    portrait_request = types.SimpleNamespace(
        generationConfig=types.SimpleNamespace(aspectRatio="portrait")
    )
    landscape_request = types.SimpleNamespace(
        generationConfig=types.SimpleNamespace(aspectRatio="landscape")
    )

    assert resolve_model_name(
        "flow_edit", request=portrait_request, model_config=MODEL_CONFIG
    ) == "flow_edit_portrait"
    assert resolve_model_name(
        "flow_edit", request=landscape_request, model_config=MODEL_CONFIG
    ) == "flow_edit"


def _stub_edit_client(monkeypatch, client, captured):
    async def fake_request(url, json_data, **kwargs):
        captured["url"] = url
        captured["json"] = json_data
        return {"operations": [{"operation": {"name": "op-1"}}]}

    monkeypatch.setattr(client, "_make_video_api_request", fake_request)
    monkeypatch.setattr(client, "_get_recaptcha_token", lambda *a, **k: _async(("tok", 1)))
    monkeypatch.setattr(client, "_warmup_flow_video_frontend_context", lambda **k: _async(None))
    monkeypatch.setattr(client, "_acquire_video_launch_gate", lambda **k: _async((True, 0, 0)))
    monkeypatch.setattr(client, "_release_video_launch_gate", lambda *a, **k: _async(None))
    monkeypatch.setattr(client, "_notify_browser_captcha_request_finished", lambda *a, **k: _async(None))
    monkeypatch.setattr(client, "_resolve_generation_retry_budget", lambda n: 1)


@pytest.mark.asyncio
async def test_generate_video_edit_remove_payload(monkeypatch):
    from src.services.flow_client import FlowClient
    client = FlowClient(proxy_manager=None)
    captured = {}
    _stub_edit_client(monkeypatch, client, captured)

    result = await client.generate_video_edit(
        at="AT", project_id="p-1", prompt="把背景墙上的画移除",
        model_key="abra_edit", aspect_ratio="VIDEO_ASPECT_RATIO_PORTRAIT",
        video_media_id="m-1", start_frame=0, end_frame=240,
    )
    assert result["operations"]
    assert captured["url"].endswith("/video:batchAsyncGenerateVideoEditVideo")
    body = captured["json"]
    assert "useV2ModelConfig" not in body
    req = body["requests"][0]
    assert req["videoModelKey"] == "abra_edit"
    assert req["videoInput"] == {"mediaId": "m-1", "startFrameIndex": 0, "endFrameIndex": 240}
    assert req["outputSpec"] == {"resolution": "VIDEO_RESOLUTION_720P"}
    assert "referenceImages" not in req
    assert req["textInput"]["structuredPrompt"]["parts"] == [{"text": "把背景墙上的画移除"}]


@pytest.mark.asyncio
async def test_generate_video_edit_insert_payload_includes_reference(monkeypatch):
    from src.services.flow_client import FlowClient
    client = FlowClient(proxy_manager=None)
    captured = {}
    _stub_edit_client(monkeypatch, client, captured)

    result = await client.generate_video_edit(
        at="AT", project_id="p-1", prompt="把这个物品放进画面",
        model_key="abra_edit", aspect_ratio="VIDEO_ASPECT_RATIO_PORTRAIT",
        video_media_id="m-1", start_frame=0, end_frame=240,
        reference_images=[{"media_id": "img-1", "handle": "flow2api_upload_1.png"}],
    )
    assert result["operations"]
    req = captured["json"]["requests"][0]
    assert req["referenceImages"] == [
        {"mediaId": "img-1", "imageUsageType": "IMAGE_USAGE_TYPE_ASSET"}
    ]
    parts = req["textInput"]["structuredPrompt"]["parts"]
    assert parts[0] == {
        "reference": {"media": {"handle": "flow2api_upload_1.png", "mediaId": "img-1"}}
    }
    assert parts[1] == {"text": "把这个物品放进画面"}


@pytest.mark.asyncio
async def test_upload_image_impl_returns_handle(monkeypatch):
    from src.services.flow_client import FlowClient
    client = FlowClient(proxy_manager=None)

    async def fake_make_request(**kwargs):
        return {"media": {"name": "new-media-id"}}

    monkeypatch.setattr(client, "_make_request", fake_make_request)

    png_bytes = b"\x89PNG\r\n\x1a\n" + b"0" * 16
    media_id, file_name = await client._upload_image_impl(
        at="test-at", image_bytes=png_bytes, project_id="project-123"
    )
    assert media_id == "new-media-id"
    assert re.fullmatch(r"flow2api_upload_\d+\.png", file_name)

    # upload_image 回归:仍只返回 media_id
    legacy_media_id = await client.upload_image(
        at="test-at", image_bytes=png_bytes, project_id="project-123"
    )
    assert legacy_media_id == "new-media-id"



# ========== Task 4: dispatch / token affinity / mediaGenerationId 落库 ==========

from types import SimpleNamespace


@pytest.mark.asyncio
async def test_task_media_generation_id_roundtrip(tmp_path):
    from src.core.database import Database
    from src.core.models import Task, Token

    db = Database(str(tmp_path / "t.db"))
    await db.init_db()
    # tasks.token_id 有外键约束,先建一个真实 token
    token_id = await db.add_token(Token(st="st-owner", email="owner@example.com"))
    await db.create_task(Task(task_id="op-1", token_id=token_id, model="abra_edit",
                              prompt="p", status="processing"))
    await db.update_task("op-1", status="completed", media_generation_id="m-xyz")
    assert await db.get_token_id_by_media_generation_id("m-xyz") == token_id
    assert await db.get_token_id_by_media_generation_id("missing") is None


@pytest.mark.asyncio
async def test_tasks_media_generation_id_index_created(tmp_path):
    from src.core.database import Database

    db = Database(str(tmp_path / "t.db"))
    await db.init_db()
    await db.check_and_migrate_db()
    async with db._connect() as conn:
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND name = ?",
            ("ix_tasks_media_generation_id",),
        )
        assert await cursor.fetchone() is not None
    # 索引存在不影响既有反查语义
    assert await db.get_token_id_by_media_generation_id("missing") is None


def _stub_token(token_id, at):
    return SimpleNamespace(
        id=token_id,
        at=at,
        email=f"token{token_id}@example.com",
        is_active=True,
        video_enabled=True,
        user_paygate_tier="PAYGATE_TIER_ONE",
        video_concurrency=-1,
    )


class _StubLoadBalancer:
    def __init__(self, selected_token):
        self._selected_token = selected_token

    async def select_token(self, **kwargs):
        return self._selected_token

    async def release_pending(self, *args, **kwargs):
        return None


class _StubTokenManager:
    async def ensure_valid_token(self, token):
        return token

    async def ensure_project_exists(self, token_id):
        return f"proj-{token_id}"

    async def record_error(self, token_id):
        return None

    async def record_usage(self, token_id, is_video=False):
        return None

    async def record_success(self, token_id):
        return None


class _StubFlowClient:
    def __init__(self):
        self.edit_calls = []
        self.upload_calls = []

    async def prefill_remote_browser_pool(self, **kwargs):
        return None

    async def _upload_image_impl(self, at, image_bytes, aspect_ratio=None, project_id=None):
        self.upload_calls.append({
            "at": at,
            "aspect_ratio": aspect_ratio,
            "project_id": project_id,
        })
        return ("uploaded-media-id", "flow2api_upload_1.png")

    async def generate_video_edit(self, **kwargs):
        self.edit_calls.append(kwargs)
        # 返回空 operations,让 handler 在分发后立刻收口,测试面保持最小
        return {"operations": []}


def _make_handler(monkeypatch, *, selected_token, db=None, flow_client=None):
    from src.services.generation_handler import GenerationHandler

    handler = GenerationHandler(
        flow_client=flow_client or _StubFlowClient(),
        token_manager=_StubTokenManager(),
        load_balancer=_StubLoadBalancer(selected_token),
        db=db or SimpleNamespace(),
        concurrency_manager=None,
        proxy_manager=None,
    )

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(handler, "_log_request", _noop)
    monkeypatch.setattr(handler, "_update_request_log_progress", _noop)
    return handler


@pytest.mark.asyncio
async def test_edit_dispatch_requires_directive(monkeypatch):
    # video_type="edit" 且无 edit_directive:
    # 断言流式输出包含编辑错误提示并以 400 结束(对照 extend 缺 id 分支)
    handler = _make_handler(monkeypatch, selected_token=_stub_token(1, "FALLBACK_AT"))

    chunks = []
    async for chunk in handler.handle_generation(
        model="flow_edit", prompt="把背景墙上的画移除", stream=True,
    ):
        chunks.append(chunk)

    output = "".join(chunks)
    assert "视频编辑需要提供源视频" in output
    assert '"status_code": 400' in output


@pytest.mark.asyncio
async def test_edit_dispatch_uses_owner_token(monkeypatch):
    # stub db.get_token_id_by_media_generation_id -> 属主 id;
    # stub db.get_token -> 活跃且 video_enabled 的属主 Token;
    # 断言 generate_video_edit 以属主 token 的 at 调用(非 load_balancer 选中的 token)
    fallback = _stub_token(1, "FALLBACK_AT")
    owner = _stub_token(7, "OWNER_AT")

    class _StubDB:
        async def get_token_id_by_media_generation_id(self, media_id):
            assert media_id == "m-owner"
            return 7

        async def get_token(self, token_id):
            return owner if token_id == 7 else None

    flow_client = _StubFlowClient()
    handler = _make_handler(
        monkeypatch, selected_token=fallback, db=_StubDB(), flow_client=flow_client
    )

    chunks = []
    async for chunk in handler.handle_generation(
        model="flow_edit",
        prompt="把背景墙上的画移除",
        stream=True,
        edit_directive={"media_id": "m-owner", "start_frame": 0, "end_frame": 240},
    ):
        chunks.append(chunk)

    assert len(flow_client.edit_calls) == 1
    call = flow_client.edit_calls[0]
    assert call["at"] == "OWNER_AT"
    assert call["video_media_id"] == "m-owner"
    assert call["start_frame"] == 0
    assert call["end_frame"] == 240


@pytest.mark.asyncio
async def test_edit_dispatch_rejects_too_many_reference_images(monkeypatch):
    # flow_edit 声明 max_images=1:携带 2 张参考图应在任何上传/client 调用前以 400 拒绝
    fallback = _stub_token(1, "FALLBACK_AT")

    class _StubDB:
        async def get_token_id_by_media_generation_id(self, media_id):
            # 属主即当前选中的 token,亲和解析直接返回 fallback
            return fallback.id

    flow_client = _StubFlowClient()
    handler = _make_handler(
        monkeypatch, selected_token=fallback, db=_StubDB(), flow_client=flow_client
    )

    chunks = []
    async for chunk in handler.handle_generation(
        model="flow_edit",
        prompt="把这个物品放进画面",
        images=[b"png-a", b"png-b"],
        stream=True,
        edit_directive={"media_id": "m-owner", "start_frame": 0, "end_frame": 240},
    ):
        chunks.append(chunk)

    output = "".join(chunks)
    assert "视频编辑最多支持 1 张参考图，当前提供了 2 张" in output
    assert '"status_code": 400' in output
    assert flow_client.upload_calls == []
    assert flow_client.edit_calls == []


# ========== Task 5: 亲和失败的机器可读 error code ==========


def test_create_error_response_supports_custom_code():
    import json as _json

    from src.services.generation_handler import GenerationHandler

    h = GenerationHandler(
        flow_client=_StubFlowClient(),
        token_manager=_StubTokenManager(),
        load_balancer=_StubLoadBalancer(_stub_token(1, "AT")),
        db=SimpleNamespace(),
        concurrency_manager=None,
        proxy_manager=None,
    )
    default = _json.loads(h._create_error_response("boom", status_code=400))
    assert default["error"]["code"] == "generation_failed"
    custom = _json.loads(
        h._create_error_response("boom", status_code=400, code="media_owner_unavailable")
    )
    assert custom["error"]["code"] == "media_owner_unavailable"
    assert custom["error"]["message"] == "boom"
    assert custom["error"]["status_code"] == 400


@pytest.mark.asyncio
async def test_edit_affinity_unknown_owner_returns_machine_code(monkeypatch):
    # 归属查不到:错误 JSON 必须带 code=media_owner_unavailable,供产品层自救识别
    class _StubDB:
        async def get_token_id_by_media_generation_id(self, media_id):
            return None

    handler = _make_handler(
        monkeypatch, selected_token=_stub_token(1, "FALLBACK_AT"), db=_StubDB()
    )

    chunks = []
    async for chunk in handler.handle_generation(
        model="flow_edit",
        prompt="把背景墙上的画移除",
        stream=True,
        edit_directive={"media_id": "m-gone", "start_frame": 0, "end_frame": 240},
    ):
        chunks.append(chunk)

    output = "".join(chunks)
    assert "不属于任何已知 token" in output
    assert '"code": "media_owner_unavailable"' in output
    assert '"status_code": 400' in output


@pytest.mark.asyncio
async def test_edit_affinity_disabled_owner_returns_machine_code(monkeypatch):
    # 属主被禁用:同样带 code=media_owner_unavailable
    disabled_owner = _stub_token(7, "OWNER_AT")
    disabled_owner.is_active = False

    class _StubDB:
        async def get_token_id_by_media_generation_id(self, media_id):
            return 7

        async def get_token(self, token_id):
            return disabled_owner if token_id == 7 else None

    handler = _make_handler(
        monkeypatch, selected_token=_stub_token(1, "FALLBACK_AT"), db=_StubDB()
    )

    chunks = []
    async for chunk in handler.handle_generation(
        model="flow_edit",
        prompt="把背景墙上的画移除",
        stream=True,
        edit_directive={"media_id": "m-owner", "start_frame": 0, "end_frame": 240},
    ):
        chunks.append(chunk)

    output = "".join(chunks)
    assert "已禁用" in output
    assert '"code": "media_owner_unavailable"' in output
    assert '"status_code": 400' in output


def test_parse_edit_directive_accepts_ten_second_range():
    from src.api.routes import _parse_edit_directive
    assert _parse_edit_directive("edit://abc?start_frame=0&end_frame=300")["end_frame"] == 300
