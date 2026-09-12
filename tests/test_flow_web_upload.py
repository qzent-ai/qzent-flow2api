import json
from unittest.mock import AsyncMock,MagicMock,patch
import pytest
from src.services.flow_web import FlowWebClient,FlowWebError
P='21111111-2222-4333-8444-555555555555'
M='31111111-2222-4333-8444-555555555555'

@pytest.mark.asyncio
@pytest.mark.parametrize('host',['flow.google.com','attacker.example'])
async def test_upload_only_sends_credentials_to_flow_origin(host):
 c=FlowWebClient(json.dumps([{'name':'SID','value':'test','domain':'.google.com'}]));c._bootstrap={'SNlM0e':'test-csrf'}
 first=MagicMock(status_code=200);first.headers={'x-goog-upload-url':'https://'+host+'/upload/v1/flow/upload/video/'+P+'?upload_id=test'}
 second=MagicMock(status_code=200);second.json.return_value={'mediaId':M,'media':{'name':M,'projectId':P}}
 session=AsyncMock();session.post.side_effect=[first,second];manager=AsyncMock();manager.__aenter__.return_value=session
 with patch('src.services.flow_web.AsyncSession',return_value=manager):
  if host=='flow.google.com':
   assert await c.upload_video(P,b'video','video/mp4')==M
   assert session.post.call_count==2
  else:
   with pytest.raises(FlowWebError,match='flow_upload_url_invalid'):await c.upload_video(P,b'video','video/mp4')
   assert session.post.call_count==1
