import json

import pytest

from src.services.flow_web import FlowWebClient, FlowWebError, cookie_header, parse_rpc


def cookies():
    return json.dumps([
        {"name": "SID", "value": "test-sid", "domain": ".google.com", "path": "/"},
        {"name": "OSID", "value": "test-osid", "domain": "flow.google.com", "path": "/"},
        {"name": "__Secure-next-auth.session-token", "value": "old-st", "domain": "labs.google"},
        {"name": "evil", "value": "no", "domain": "evilgoogle.com"},
    ])


def frame(rpc, payload):
    return ")]}'\n\n123\n" + json.dumps([["wrb.fr", rpc, json.dumps(payload)]])


def test_only_matching_cookies_are_sent():
    assert cookie_header(cookies()) == "SID=test-sid; OSID=test-osid"


def test_rejects_header_injection():
    with pytest.raises(FlowWebError):
        cookie_header(json.dumps([{"name": "SID", "value": "a\r\nx: y", "domain": ".google.com"}]))


def test_rpc_decodes_matching_frame_and_unicode():
    assert parse_rpc(frame("other", []) + "\n" + frame("test", ["项目"]), "test") == ["项目"]


def test_rpc_http_200_can_be_business_error():
    with pytest.raises(FlowWebError) as exc:
        parse_rpc(")]}'\n" + json.dumps([["er", "test", 16, "secret diagnostic"]]), "test")
    assert exc.value.code == "flow_session_expired"
    assert "secret" not in str(exc.value)


def test_login_html_is_not_a_success():
    with pytest.raises(FlowWebError):
        parse_rpc("<html>login</html>", "test")


@pytest.mark.asyncio
async def test_bootstrap_requires_account_not_only_csrf(monkeypatch):
    client = FlowWebClient(cookies())
    async def request(*args, **kwargs):
        return '<script>window.WIZ_global_data={"SNlM0e":"csrf","FdrFJe":"sid"};</script>'
    monkeypatch.setattr(client, "_request", request)
    with pytest.raises(FlowWebError) as exc:
        await client.authenticate()
    assert exc.value.code == "flow_session_unverified"


@pytest.mark.asyncio
async def test_bootstrap_recognizes_account_without_legacy_at(monkeypatch):
    client = FlowWebClient(cookies())
    async def request(*args, **kwargs):
        return '<script>window.WIZ_global_data={"SNlM0e":"csrf","FdrFJe":"sid","oPEP7c":"test@example.com"};</script>'
    monkeypatch.setattr(client, "_request", request)
    assert (await client.authenticate())["email"] == "test@example.com"


@pytest.mark.asyncio
async def test_create_project_checks_authoritative_id(monkeypatch):
    client = FlowWebClient(cookies())
    calls = []
    async def rpc(name, args):
        calls.append((name, args))
        return ["projects/11111111-2222-4333-8444-555555555555", ["test"]]
    monkeypatch.setattr(client, "rpc", rpc)
    assert await client.create_project("test") == "11111111-2222-4333-8444-555555555555"
    assert calls == [("jHPbke", ["projects/*", [None, ["test"]], [None, 22]])]


@pytest.mark.asyncio
async def test_project_response_does_not_accept_unrelated_nested_uuid(monkeypatch):
    from unittest.mock import AsyncMock
    client = FlowWebClient(cookies())
    monkeypatch.setattr(client, 'rpc', AsyncMock(return_value=[None, ['11111111-2222-4333-8444-555555555555']]))
    with pytest.raises(FlowWebError, match='flow_project_invalid'):
        await client.create_project('test')


@pytest.mark.asyncio
@pytest.mark.parametrize('wire,expected', [(1,'PAYGATE_TIER_ONE'),(2,'PAYGATE_TIER_TWO'),(3,'PAYGATE_TIER_NOT_PAID'),(0,None),(999,None)])
async def test_credits_maps_upstream_enum_without_inventing_free(monkeypatch,wire,expected):
    from unittest.mock import AsyncMock
    client = FlowWebClient(cookies())
    monkeypatch.setattr(client,'rpc',AsyncMock(return_value=[104,wire,2,2,None,104]))
    assert await client.get_credits() == {'credits':104,'userPaygateTier':expected}


@pytest.mark.asyncio
async def test_bad_credits_response_is_not_zero(monkeypatch):
    from unittest.mock import AsyncMock
    client = FlowWebClient(cookies())
    monkeypatch.setattr(client,'rpc',AsyncMock(return_value=[]))
    with pytest.raises(FlowWebError,match='flow_response_invalid'):
        await client.get_credits()

@pytest.mark.parametrize('wire,code',[(3,'flow_invalid_request'),(7,'flow_permission_denied'),(8,'flow_quota_exceeded'),(16,'flow_session_expired'),(13,'flow_upstream_failed')])
def test_wrapped_rpc_error_keeps_numeric_upstream_code(wire,code):
 with pytest.raises(FlowWebError) as caught:
  parse_rpc(json.dumps([['wrb.fr','test',None,None,None,[wire],'generic']]),'test')
 assert caught.value.code==code
 assert str(wire) in str(caught.value)

@pytest.mark.asyncio
@pytest.mark.parametrize('html,code', [('<html>unexpected</html>','flow_session_unverified'),('<script>WIZ_global_data={"FdrFJe":"fixture"};</script>','flow_cookies_refresh_required')])
async def test_unknown_page_is_not_reported_as_expired(monkeypatch,html,code):
    from unittest.mock import AsyncMock
    client=FlowWebClient(cookies());monkeypatch.setattr(client,'_request',AsyncMock(return_value=html))
    with pytest.raises(FlowWebError) as exc:await client.authenticate()
    assert exc.value.code==code
