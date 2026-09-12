"""New Flow wire fixtures: exact workflow versions must survive edits."""
from unittest.mock import AsyncMock
import pytest
from src.services.flow_web_video import FlowWebVideo, parse_workflow
from src.services.flow_web import FlowWebError

W='11111111-2222-4333-8444-555555555555'
P='21111111-2222-4333-8444-555555555555'
M='31111111-2222-4333-8444-555555555555'

def record(status=3):
 return [W,P,M,'CAE',None,[None,'prompt',None,None,None,None,None,None,[status]],None,[[None,None,None,None,None,None,None,'prompt','https://flow-content.google/test.mp4'],[640,360,[4]]]]

def test_public_media_id_is_version_not_mutable_gallery_tile():
 parsed=parse_workflow(record())
 assert parsed['media_id']==W
 assert parsed['tile_id']==M
 assert parsed['status']==3
 assert parsed['url']=='https://flow-content.google/test.mp4'

@pytest.mark.parametrize('bad',[[],['unexpected'],[W,P,M,'other']])
def test_reject_unrecognized_record(bad):
 with pytest.raises(FlowWebError):parse_workflow(bad)

@pytest.mark.asyncio
async def test_submit_text_keeps_requested_model_and_aspect():
 client=AsyncMock();client.rpc.return_value=[None,100,[[record(2)]]]
 video=FlowWebVideo(client)
 out=await video.submit(P,'hello','abra_t2v_4s',2,'captcha')
 assert out['media_id']==W
 name,args=client.rpc.call_args.args
 assert name=='YhhmEf'
 assert args[0][0][1:3]==['abra_t2v_4s',2]
 assert args[1][-1]==['captcha',1]

@pytest.mark.asyncio
async def test_edit_uses_exact_workflow_and_no_unverified_feature_flags():
 client=AsyncMock();client.rpc.return_value=[record(2)]
 video=FlowWebVideo(client)
 await video.submit(P,'red','abra_edit',2,'captcha',source=record(),start_frame=0,end_frame=96)
 name,args=client.rpc.call_args.args
 assert name=='jIps6'
 assert args[0][0][0]==[None,W,0,96]
 assert len(args[0][0])==5
 assert args[0][0][4][1]==M

@pytest.mark.asyncio
async def test_wrong_project_source_rejected_before_charging():
 client=AsyncMock();video=FlowWebVideo(client)
 with pytest.raises(FlowWebError,match='media_owner_unavailable'):
  await video.submit(M,'red','abra_edit',2,'captcha',source=record(),start_frame=0,end_frame=96)
 client.rpc.assert_not_called()

def test_download_url_must_be_google_media_not_arbitrary_host():
 r=record();r[7][0][8]='http://127.0.0.1/admin'
 with pytest.raises(FlowWebError):parse_workflow(r)

@pytest.mark.asyncio
async def test_edit_submission_cai_is_an_accepted_workflow_version():
 client=AsyncMock();r=record(6);r[3]='CAI';client.rpc.return_value=[None,1023,[],[r]]
 result=await FlowWebVideo(client).submit(P,'red','abra_edit',2,'captcha',source=record(),start_frame=0,end_frame=96)
 assert result['media_id']==W
 assert result['status']==6

@pytest.mark.asyncio
@pytest.mark.parametrize('mode,refs,rpc',[('references',[M],'MZZa6b'),('start',[M],'eb1hJf'),('start_end',[M,W],'nprQif')])
async def test_video_image_inputs_use_matching_native_rpc(mode,refs,rpc):
 c=AsyncMock();c.rpc.return_value=[record(2)]
 await FlowWebVideo(c).submit(P,'test','model',2,'captcha',mode=mode,references=refs)
 name,args=c.rpc.call_args.args
 assert name==rpc
 assert args[0][0][0]==[None,None,[[['test']]]]
 if mode=='references':assert args[0][0][1]==[[None,M]]
 else:assert args[0][0][4]==[None,M]
 if mode=='start_end':assert args[0][0][5]==[None,W]


def test_failed_record_keeps_unknown_public_error_without_echoing_private_text():
 r=record(4);r[5][8].append([13,'PUBLIC_ERROR_FUTURE_REASON','private cookie text'])
 p=parse_workflow(r)
 assert p['error_codes']==['PUBLIC_ERROR_FUTURE_REASON']
 assert 'private cookie' not in str(p)

@pytest.mark.parametrize('step',[1,2,3,4,127,128,255,1000])
def test_media_step_identifier_is_encoded_number_not_fixed_enum(step):
 import base64
 value=step;wire=[8]
 while value>127:
  wire.append((value&127)|128);value>>=7
 wire.append(value)
 r=record();r[3]=base64.urlsafe_b64encode(bytes(wire)).decode().rstrip('=')
 assert parse_workflow(r)['media_id']==W

@pytest.mark.asyncio
async def test_third_edit_version_is_recognized_without_resubmitting():
 c=AsyncMock();r=record(6);r[3]='CAM';c.rpc.return_value=[None,900,[],[r]]
 result=await FlowWebVideo(c).submit(P,'green','abra_edit',2,'captcha',source=record(),start_frame=0,end_frame=96)
 assert result['media_id']==W
 c.rpc.assert_awaited_once()
