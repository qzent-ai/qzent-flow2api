from unittest.mock import AsyncMock, Mock

import pytest

from src.core.models import Token
from src.services.token_manager import TokenManager


def manager(existing=None):
    db = Mock()
    db.get_token_by_email = AsyncMock(return_value=existing)
    db.add_token = AsyncMock(return_value=9)
    db.add_project = AsyncMock(return_value=2)
    db.update_token = AsyncMock()
    db.get_token = AsyncMock(return_value=existing)
    m = TokenManager(db, Mock())
    client = Mock()
    client.authenticate = AsyncMock(return_value={"email": "test@example.com"})
    client.get_credits = AsyncMock(return_value={"credits":104,"userPaygateTier":"PAYGATE_TIER_ONE"})
    client.create_project = AsyncMock(return_value="11111111-2222-4333-8444-555555555555")
    client.cookies = [{"name": "SID", "value": "test", "domain": ".google.com"}]
    m.get_flow_web_client = AsyncMock(return_value=client)
    return m, db, client


@pytest.mark.asyncio
async def test_new_account_does_not_exchange_legacy_st():
    m, db, client = manager()
    token, action = await m.sync_flow_web_token("[]")
    assert action == "added"
    assert token.protocol_mode == "flow_web"
    assert token.at is None and token.at_expires is None
    assert token.st.startswith("flow-web:")
    assert token.email == "test@example.com"
    client.create_project.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_preserves_account_id_and_existing_project():
    old = Token(id=3, st="old", email="test@example.com", current_project_id="existing", is_active=False)
    m, db, client = manager(old)
    _, action = await m.sync_flow_web_token("[]", auto_enable=False)
    assert action == "updated"
    fields = db.update_token.await_args.kwargs
    assert db.update_token.await_args.args == (3,)
    assert fields["at"] is None and fields["at_expires"] is None
    assert "current_project_id" not in fields
    assert "is_active" not in fields
    client.create_project.assert_not_awaited()


@pytest.mark.asyncio
async def test_web_account_validation_never_refreshes_labs_at():
    old = Token(id=3, st="flow-web:3", email="test@example.com", protocol_mode="flow_web", google_cookies="[]")
    m, db, client = manager(old)
    assert await m.ensure_valid_token(old) is old
    client.authenticate.assert_awaited_once()


@pytest.mark.asyncio
async def test_swapped_cookie_account_is_rejected():
    old = Token(id=3, st="flow-web:3", email="other@example.com", protocol_mode="flow_web", google_cookies="[]")
    m, db, client = manager(old)
    with pytest.raises(ValueError, match="flow_account_mismatch"):
        await m.ensure_valid_token(old)


def test_web_account_never_schedules_labs_at_refresh():
    token = Token(id=3, st='local', email='test@example.com', protocol_mode='flow_web')
    m, _, _ = manager(token)
    assert m.needs_at_refresh(token) is False


@pytest.mark.asyncio
async def test_manual_refresh_validates_web_session_without_legacy_fallback():
    token = Token(id=3, st='local', email='test@example.com', protocol_mode='flow_web', google_cookies='[]')
    m, db, client = manager(token)
    m._do_refresh_at = AsyncMock()
    assert await m._refresh_at(3) is True
    m._do_refresh_at.assert_not_awaited()
    assert db.update_token.await_args.kwargs['last_st_refresh_result'] == '新版 Flow 会话已验证'


@pytest.mark.asyncio
async def test_web_credits_refresh_persists_real_balance_and_tier():
    token = Token(id=3, st='local', email='test@example.com', protocol_mode='flow_web', google_cookies='[]')
    m, db, client = manager(token)
    assert await m.refresh_credits(3) == 104
    fields=db.update_token.await_args.kwargs
    assert fields['credits'] == 104
    assert fields['user_paygate_tier'] == 'PAYGATE_TIER_ONE'


@pytest.mark.asyncio
async def test_sync_sets_real_credits_and_tier():
    m, db, client = manager()
    token, _ = await m.sync_flow_web_token('[]')
    assert token.credits == 104
    assert token.user_paygate_tier == 'PAYGATE_TIER_ONE'

@pytest.mark.asyncio
async def test_sync_does_not_reenable_manually_disabled_account():
    old = Token(id=3, st='local', email='test@example.com', is_active=False)
    m, db, client = manager(old)
    await m.sync_flow_web_token('[]', auto_enable=True)
    assert 'is_active' not in db.update_token.await_args.kwargs

@pytest.mark.asyncio
async def test_sync_recovers_only_session_paused_account():
    old = Token(id=3, st='local', email='test@example.com', is_active=False, ban_reason='flow_session_invalid')
    m, db, client = manager(old)
    await m.sync_flow_web_token('[]', auto_enable=True)
    assert db.update_token.await_args.kwargs['is_active'] is True

@pytest.mark.asyncio
@pytest.mark.parametrize('code,paused', [('flow_cookies_refresh_required',True),('flow_connection_failed',False),('flow_session_unverified',False)])
async def test_validation_records_error_and_only_pauses_invalid_session(code, paused):
    from src.services.flow_web import FlowWebError
    old = Token(id=3, st='local', email='test@example.com', protocol_mode='flow_web', google_cookies='[]')
    m, db, client = manager(old)
    client.authenticate.side_effect=FlowWebError(code,'fixture')
    with pytest.raises(FlowWebError): await m.ensure_valid_token(old)
    fields=db.update_token.await_args.kwargs
    assert code in fields['last_st_refresh_result']
    assert (fields.get('is_active') is False) is paused

@pytest.mark.asyncio
async def test_validation_cache_expires_on_cookie_change_and_manual_check():
    old=Token(id=3,st='local',email='test@example.com',protocol_mode='flow_web',google_cookies='[]')
    m,db,client=manager(old)
    await m.ensure_valid_token(old)
    await m.ensure_valid_token(old)
    assert client.authenticate.await_count==1
    old.google_cookies='[{}]'
    await m.ensure_valid_token(old)
    assert client.authenticate.await_count==2
    await m.ensure_valid_token(old,force=True)
    assert client.authenticate.await_count==3
