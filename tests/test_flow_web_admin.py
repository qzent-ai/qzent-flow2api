from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from src.api import admin
from src.core.models import Token
from src.services.flow_web import FlowWebError


@pytest.mark.asyncio
async def test_plugin_accepts_new_cookies_without_st(monkeypatch):
    monkeypatch.setattr(admin, "_verify_plugin_connection_token", AsyncMock())
    db = Mock(get_plugin_config=AsyncMock(return_value=Mock(auto_enable_on_update=False)))
    manager = Mock(sync_flow_web_token=AsyncMock(return_value=(Token(id=8, st="local", email="test@example.com", protocol_mode="flow_web"), "updated")))
    monkeypatch.setattr(admin, "db", db)
    monkeypatch.setattr(admin, "token_manager", manager)
    result = await admin.plugin_update_token({"protocol_mode": "flow_web", "google_cookies": "[]"})
    assert result["success"] is True
    assert result["protocol_mode"] == "flow_web"
    assert "会话" in result["message"]
    manager.sync_flow_web_token.assert_awaited_once_with("[]", auto_enable=False)


@pytest.mark.asyncio
async def test_plugin_returns_structured_auth_error(monkeypatch):
    monkeypatch.setattr(admin, "_verify_plugin_connection_token", AsyncMock())
    monkeypatch.setattr(admin, "db", Mock(get_plugin_config=AsyncMock(return_value=Mock(auto_enable_on_update=True))))
    monkeypatch.setattr(admin, "token_manager", Mock(sync_flow_web_token=AsyncMock(side_effect=FlowWebError("flow_session_expired", "请重新同步", 401))))
    with pytest.raises(HTTPException) as exc:
        await admin.plugin_update_token({"protocol_mode": "flow_web", "google_cookies": "[]"})
    assert exc.value.status_code == 401
    assert exc.value.detail["code"] == "flow_session_expired"


@pytest.mark.asyncio
async def test_web_edit_preserves_noncredential_settings(monkeypatch):
    manager = Mock(sync_flow_web_token=AsyncMock(), update_token=AsyncMock())
    monkeypatch.setattr(admin, 'token_manager', manager)
    monkeypatch.setattr(admin, 'concurrency_manager', None)
    await admin.update_token(8, admin.UpdateTokenRequest(protocol_mode='flow_web', google_cookies='[]', remark='my account', image_enabled=False, video_concurrency=2))
    manager.update_token.assert_awaited_once()
    fields = manager.update_token.await_args.kwargs
    assert fields['remark'] == 'my account'
    assert fields['image_enabled'] is False
    assert fields['video_concurrency'] == 2
    assert 'st' not in fields and 'google_cookies' not in fields


@pytest.mark.asyncio
async def test_legacy_plugin_rejects_expired_at_instead_of_false_success(monkeypatch):
    monkeypatch.setattr(admin, '_verify_plugin_connection_token', AsyncMock())
    monkeypatch.setattr(admin, 'db', Mock(get_plugin_config=AsyncMock(return_value=Mock(auto_enable_on_update=True))))
    manager = Mock(flow_client=Mock(st_to_at=AsyncMock(return_value={'access_token':'fixture', 'expires':'2000-01-01T00:00:00Z', 'user':{'email':'test@example.com'}})))
    monkeypatch.setattr(admin, 'token_manager', manager)
    with pytest.raises(HTTPException) as exc:
        await admin.plugin_update_token({'session_token':'fixture'})
    assert exc.value.status_code == 401
    assert 'legacy_session_expired' in str(exc.value.detail)


@pytest.mark.asyncio
async def test_web_import_without_old_st(monkeypatch):
    token = Token(id=8, st='local', email='test@example.com', protocol_mode='flow_web')
    manager = Mock(get_all_tokens=AsyncMock(return_value=[]), sync_flow_web_token=AsyncMock(return_value=(token,'added')), update_token=AsyncMock(), disable_token=AsyncMock())
    monkeypatch.setattr(admin, 'token_manager', manager)
    monkeypatch.setattr(admin, 'concurrency_manager', None)
    result = await admin.import_tokens(admin.ImportTokensRequest(tokens=[admin.ImportTokenItem(protocol_mode='flow_web', google_cookies='[]', is_active=False)]))
    assert result['added'] == 1 and not result['errors']
    manager.disable_token.assert_awaited_once_with(8)


@pytest.mark.asyncio
async def test_plugin_url_preserves_https(monkeypatch):
    from starlette.requests import Request
    monkeypatch.setattr(admin, 'db', Mock(get_plugin_config=AsyncMock(return_value=Mock(connection_token='fixture', auto_enable_on_update=True))))
    request = Request({'type':'http','scheme':'https','server':('example.com',443),'path':'/api/plugin/config','query_string':b'', 'headers':[(b'host',b'example.com')]})
    result = await admin.get_plugin_config(request)
    assert result['config']['connection_url'] == 'https://example.com/api/plugin/update-token'
