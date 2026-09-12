import json
from unittest.mock import AsyncMock, Mock
import pytest
from src.services.generation_handler import GenerationHandler
from src.core.database import Database
from src.core.models import RequestLog
from src.api import admin

@pytest.mark.asyncio
@pytest.mark.parametrize('model,images,operation',[
 ('flow_edit',None,'edit_video'),
 ('omni_4s',None,'generate_video'),
 ('veo_3_1_i2v_s_landscape',[b'fixture'],'generate_video'),
 ('gemini-3.1-flash-image-landscape',[b'fixture'],'edit_image'),
 ('gemini-3.1-flash-image-landscape',None,'generate_image'),
])
@pytest.mark.parametrize('stream',[False,True])
async def test_failed_requests_keep_actual_operation(model,images,operation,stream):
 h=GenerationHandler.__new__(GenerationHandler)
 h.flow_client=Mock()
 h.load_balancer=Mock(select_token=AsyncMock(return_value=None),get_unavailable_reason=AsyncMock(return_value='fixture unavailable'))
 h._log_request=AsyncMock(return_value=1)
 async for _ in h.handle_generation(model,'fixture',images=images,stream=stream):pass
 assert all(call.kwargs['operation']==operation for call in h._log_request.await_args_list)

@pytest.mark.asyncio
@pytest.mark.parametrize('operation,payload,expected',[
 ('generate_video',{'model':'flow_edit'},'edit_video'),
 ('generate_image',{'model':'gemini-3.1-flash-image-landscape','has_images':True},'edit_image'),
 ('generate_video',{'model':'veo_3_1_i2v_s_landscape','has_images':True},'generate_video'),
 ('generate_video',{'model':'unknown'},'generate_video'),
 ('generate_image',{'has_images':True},'generate_image'),
 ('edit_video',{},'edit_video'),
 ('generate_video','malformed','generate_video'),
])
async def test_history_list_and_detail_agree_without_exposing_payload(tmp_path,monkeypatch,operation,payload,expected):
 db=Database(str(tmp_path/'flow.db'));await db.init_db()
 log_id=await db.add_request_log(RequestLog(operation=operation,request_body=json.dumps(payload) if isinstance(payload,dict) else payload,status_code=200,duration=1))
 monkeypatch.setattr(admin,'db',db)
 listing=await admin.get_logs(limit=100,token='fixture')
 detail=await admin.get_log_detail(log_id,token='fixture')
 assert listing[0]['operation']==detail['operation']==expected
 assert 'request_body' not in listing[0]
