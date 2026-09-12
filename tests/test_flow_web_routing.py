from unittest.mock import AsyncMock, Mock
import pytest
from src.core.models import Token
from src.services.load_balancer import LoadBalancer

@pytest.mark.asyncio
async def test_new_web_session_is_eligible_after_cookie_validation():
    token = Token(id=3, st='local', email='test@example.com', protocol_mode='flow_web')
    manager = Mock(get_active_tokens=AsyncMock(return_value=[token]), ensure_valid_token=AsyncMock(return_value=token), needs_at_refresh=Mock(return_value=False))
    balancer = LoadBalancer(manager)
    balancer._check_extension_route = AsyncMock(return_value=(True, None))
    assert await balancer.select_token(for_video_generation=True) is token
    manager.ensure_valid_token.assert_awaited_once_with(token)

@pytest.mark.asyncio
async def test_expired_web_account_does_not_block_healthy_account():
    from unittest.mock import patch
    from src.services.flow_web import FlowWebError
    bad=Token(id=1,st='local1',email='bad@example.com',protocol_mode='flow_web')
    good=Token(id=2,st='local2',email='good@example.com',protocol_mode='flow_web')
    async def validate(token):
        if token.id==1:raise FlowWebError('flow_session_expired','expired',401)
        return token
    manager=Mock(get_active_tokens=AsyncMock(return_value=[bad,good]),ensure_valid_token=AsyncMock(side_effect=validate),needs_at_refresh=Mock(return_value=False))
    balancer=LoadBalancer(manager);balancer._check_extension_route=AsyncMock(return_value=(True,None))
    with patch('src.services.load_balancer.config') as cfg:
        cfg.call_logic_mode='polling'
        assert await balancer.select_token(for_video_generation=True) is good
    assert manager.ensure_valid_token.await_count==2
