from unittest.mock import AsyncMock
import pytest
from src.services.flow_web_image import FlowWebImage
from test_flow_web_video import W,P,M

@pytest.mark.asyncio
async def test_image_response_uses_immutable_media_id_and_reference_ids():
 details=[None]*14;details[13]='https://flow-content.google/image.png'
 c=AsyncMock();c.rpc.return_value=[[[W,None,M,None,None,None,[details,None,[640,360]]]],[[M,None,None,None,P]]]
 result=await FlowWebImage(c).generate(P,'blue cube','NARWHAL',3,'captcha',references=[W])
 assert result['media_id']==W
 assert result['url']=='https://flow-content.google/image.png'
 name,args=c.rpc.call_args.args
 assert name=='ogiZ0b'
 assert args[1][0][2]==[[W,None,None,None,1]]
 assert args[1][0][4]==3

@pytest.mark.asyncio
async def test_uploaded_image_must_belong_to_target_project():
 from src.services.flow_web import FlowWebError
 c=AsyncMock();c.rpc.return_value=[[W,M,P,'CAE',None,[]]]
 with pytest.raises(FlowWebError):await FlowWebImage(c).upload(P,b'png','image/png','captcha')
