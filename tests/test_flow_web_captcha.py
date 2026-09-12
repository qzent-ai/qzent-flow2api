from unittest.mock import AsyncMock,MagicMock,patch
import pytest
from src.services.flow_client import FlowClient

@pytest.mark.asyncio
async def test_new_flow_captcha_uses_new_origin_without_logging_solution():
 flow=FlowClient.__new__(FlowClient);flow.proxy_manager=None
 flow.get_request_fingerprint=lambda:{}
 flow._merge_request_fingerprint=lambda *a,**k:None
 flow._get_primary_accept_language=lambda:"en-US"
 flow._resolve_recaptcha_runtime_settings=lambda *a,**k:{'task_type':'RecaptchaV3TaskProxylessM1','min_score':None,'website_key':'site','page_action':'VIDEO_GENERATION'}
 session=AsyncMock()
 first=MagicMock();first.json.return_value={'taskId':'task'};first.status_code=200
 second=MagicMock();second.json.return_value={'status':'ready','solution':{'gRecaptchaResponse':'secret-solution','userAgent':'browser-agent'}};second.status_code=200
 session.post.side_effect=[first,second]
 manager=AsyncMock();manager.__aenter__.return_value=session
 with patch('src.services.flow_client.AsyncSession',return_value=manager),patch('src.services.flow_client.config') as cfg,patch('src.services.flow_client.debug_logger') as logger,patch('asyncio.sleep',new=AsyncMock()):
  cfg.yescaptcha_api_key='private-key';cfg.yescaptcha_base_url='https://api.yescaptcha.com'
  result=await flow._get_api_captcha_token('yescaptcha','project',action='VIDEO_GENERATION',user_agent='browser-agent',website_url='https://flow.google.com/project/project')
  assert result==('secret-solution','browser-agent')
  assert session.post.call_args_list[0].kwargs['json']['task']['websiteURL']=='https://flow.google.com/project/project'
  assert 'secret-solution' not in str(logger.mock_calls)
  assert 'private-key' not in str(logger.mock_calls)
