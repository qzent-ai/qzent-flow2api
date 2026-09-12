from types import SimpleNamespace
from unittest.mock import AsyncMock,Mock,patch
import pytest
from src.services.flow_web_generation import generate_video
from src.services.flow_web import FlowWebError
from test_flow_web_video import record,W,P


def setup():
 h=Mock();h.db.create_task=AsyncMock();h.db.update_task=AsyncMock();h._update_request_log_progress=AsyncMock()
 client=Mock();client.proxy=None;client.rpc=AsyncMock(side_effect=[[record(2)],record(3)])
 h.token_manager.get_flow_web_client=AsyncMock(return_value=client)
 h.flow_client._get_api_captcha_token=AsyncMock(return_value=('test','user-agent'))
 h.file_cache.download_and_cache=AsyncMock(return_value='test.mp4');h._get_base_url.return_value='http://flow2api:8000'
 h._create_stream_chunk=lambda x,**kw:x
 h._mark_generation_succeeded=lambda r:r.update(success=True)
 t=SimpleNamespace(id=1,google_cookies='[]',proxy_url=None,user_paygate_tier='PAYGATE_TIER_ONE')
 return h,t,client

@pytest.mark.asyncio
async def test_success_persists_exact_version_and_returns_cached_url():
 h,t,c=setup();state={};result={}
 with patch('src.services.flow_web_generation.config') as cfg,patch('asyncio.sleep',new=AsyncMock()):
  cfg.captcha_method='yescaptcha';cfg.cache_enabled=True
  out=[x async for x in generate_video(h,t,P,{'type':'video','video_type':'t2v','model_key':'abra_t2v_4s','aspect_ratio':'VIDEO_ASPECT_RATIO_LANDSCAPE'},'test',None,True,result,state,{})]
 assert state['generated_assets']['mediaGenerationId']==W
 assert W in out[-1]
 assert 'http://flow2api:8000/tmp/test.mp4' in out[-1]
 assert h.db.update_task.await_args.kwargs['media_generation_id']==W
 assert result['success'] is True

@pytest.mark.asyncio
async def test_cache_failure_never_claims_success_or_leaks_signed_url():
 h,t,c=setup();h.file_cache.download_and_cache.side_effect=RuntimeError('private download url')
 result={}
 with patch('src.services.flow_web_generation.config') as cfg,patch('asyncio.sleep',new=AsyncMock()):
  cfg.captcha_method='yescaptcha';cfg.cache_enabled=True
  with pytest.raises(FlowWebError,match='flow_cache_failed'):
   _=[x async for x in generate_video(h,t,P,{'type':'video','video_type':'t2v','model_key':'abra_t2v_4s','aspect_ratio':'VIDEO_ASPECT_RATIO_LANDSCAPE'},'test',None,True,result,{}, {})]
 assert not result.get('success')
 assert h.db.update_task.await_args.kwargs['status']=='failed'


def test_nonstream_video_response_preserves_version_for_next_edit():
 import json
 from src.services.generation_handler import GenerationHandler
 h=GenerationHandler.__new__(GenerationHandler)
 response=json.loads(h._create_completion_response('https://example.com/result.mp4',media_type='video',media_id=W))
 assert f"data-media-id='{W}'" in response['choices'][0]['message']['content']

@pytest.mark.asyncio
async def test_no_references_does_not_import_image_decoder():
 import sys
 from src.services.flow_web_generation import upload_references
 with patch.dict(sys.modules,{'PIL':None}):
  assert await upload_references(Mock(),Mock(),P,None)==[]

@pytest.mark.parametrize('code',['flow_operation_unsupported','flow_cache_failed','recaptcha_failed','flow_invalid_request','invalid_image_count'])
def test_local_failures_do_not_disable_healthy_google_account(code):
 from src.services.generation_handler import GenerationHandler
 h=GenerationHandler.__new__(GenerationHandler)
 assert not h._should_count_token_error(FlowWebError(code,'本地配置错误'))


def test_missing_server_dependency_is_not_a_google_account_fault():
 from src.services.generation_handler import GenerationHandler
 h=GenerationHandler.__new__(GenerationHandler)
 assert not h._should_count_token_error(ModuleNotFoundError('PIL'))
