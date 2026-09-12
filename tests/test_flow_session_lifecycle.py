import json
from unittest.mock import AsyncMock, Mock
import pytest
from src.core.database import Database
from src.core.models import Token
from src.services.flow_web import FlowWebError
from src.services.token_manager import TokenManager

@pytest.mark.asyncio
async def test_pause_sync_recover_and_manual_disable_persist(tmp_path):
    db=Database(str(tmp_path/'flow.db'));await db.init_db()
    cookies=json.dumps([{'name':'SID','domain':'.google.com','value':'fixture','path':'/'}])
    token=Token(st='local',email='test@example.com',protocol_mode='flow_web',google_cookies=cookies)
    token.id=await db.add_token(token)
    m=TokenManager(db,Mock());client=Mock(cookies=json.loads(cookies))
    client.authenticate=AsyncMock(side_effect=FlowWebError('flow_cookies_refresh_required','fixture'))
    client.get_credits=AsyncMock(return_value={'credits':100,'userPaygateTier':'PAYGATE_TIER_ONE'})
    m.get_flow_web_client=AsyncMock(return_value=client)
    with pytest.raises(FlowWebError):await m.ensure_valid_token(token)
    paused=await db.get_token(token.id)
    assert not paused.is_active and paused.ban_reason=='flow_session_invalid'
    assert not await m.get_active_tokens()
    client.authenticate.side_effect=None;client.authenticate.return_value={'email':token.email}
    recovered,_=await m.sync_flow_web_token(cookies)
    assert recovered.is_active and recovered.ban_reason is None
    await m.disable_token(token.id)
    disabled,_=await m.sync_flow_web_token(cookies)
    assert not disabled.is_active and disabled.ban_reason=='manual'
    assert disabled.last_st_refresh_result=='新版 Flow 会话已验证'

@pytest.mark.asyncio
@pytest.mark.parametrize('status,location,code',[(403,'','flow_access_denied'),(302,'https://accounts.google.com/ServiceLogin','flow_cookies_refresh_required'),(302,'https://example.com/','flow_session_unverified'),(401,'','flow_session_expired')])
async def test_transport_classification(monkeypatch,status,location,code):
    import src.services.flow_web as module
    response=Mock(status_code=status,headers={'Location':location},text='')
    session=AsyncMock();session.request.return_value=response;session.__aenter__.return_value=session
    monkeypatch.setattr(module,'AsyncSession',Mock(return_value=session))
    client=module.FlowWebClient(json.dumps([{'name':'SID','value':'fixture','domain':'.google.com'}]))
    with pytest.raises(FlowWebError) as e:await client.authenticate()
    assert e.value.code==code
