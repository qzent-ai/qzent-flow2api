import json
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
from src.api import admin
from src.core.database import Database
from src.core.models import Token

@pytest.mark.asyncio
async def test_sync_audit_success_failure_and_no_secrets(tmp_path,monkeypatch):
 db=Database(str(tmp_path/'flow.db'));await db.init_db();monkeypatch.setattr(admin,'db',db)
 token_id=await db.add_token(Token(st='fixture',email='fixture@example.com'))
 monkeypatch.setattr(admin,'_plugin_update_token',AsyncMock(return_value={'success':True,'action':'updated','token_id':token_id}))
 await admin.plugin_update_token({'google_cookies':'private-cookie'},authorization='Bearer private-key')
 monkeypatch.setattr(admin,'_plugin_update_token',AsyncMock(side_effect=HTTPException(401,detail={'code':'flow_session_expired','message':'private-cookie private-key'})))
 with pytest.raises(HTTPException):await admin.plugin_update_token({},authorization='Bearer private-key')
 rows=await admin.get_cookie_sync_logs(limit=100,token='fixture')
 assert len(rows)==2 and rows[0]['success']==0 and rows[1]['success']==1
 assert rows[1]['account']=='fixture@example.com'
 assert rows[0]['error_code']=='flow_session_expired'
 assert 'private-' not in json.dumps(rows)

@pytest.mark.asyncio
async def test_audit_failure_does_not_change_sync_result(monkeypatch):
 monkeypatch.setattr(admin,'db',type('Broken',(),{'add_cookie_sync_log':AsyncMock(side_effect=RuntimeError())})())
 monkeypatch.setattr(admin,'_plugin_update_token',AsyncMock(return_value={'success':True,'action':'updated'}))
 assert (await admin.plugin_update_token({},authorization='fixture'))['success']

@pytest.mark.asyncio
async def test_sync_logs_require_admin():
 import httpx
 from fastapi import FastAPI
 app=FastAPI();app.include_router(admin.router)
 async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://fixture') as client:
  assert (await client.get('/api/cookie-sync/logs')).status_code==401
