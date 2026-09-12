"""Run explicitly: .venv/bin/python tests/ui/browser_smoke.py (Chromium required)."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    errors, calls, edits = [], [], []
    page.on('pageerror', lambda e: errors.append(str(e)))
    def route(r):
        path = r.request.url.split('fixture.test')[-1]
        calls.append(path)
        if path in ('/manage', '/test'):
            r.fulfill(content_type='text/html', body=(ROOT / 'static' / (path[1:]+'.html')).read_text())
        elif path == '/api/tokens': r.fulfill(json=[{'id':9,'email':'fixture@example.com','protocol_mode':'flow_web','is_active':False,'ban_reason':'flow_session_invalid','last_st_refresh_at':'2026-09-12T00:00:00Z','last_st_refresh_result':'请同步最新 Cookies，错误码：flow_cookies_refresh_required'}])
        elif path == '/api/stats': r.fulfill(json={'total_tokens': 2, 'active_tokens': 2})
        elif path == '/v1/models': r.fulfill(json={'data':[{'id':'flow_edit','description':'Edit'},{'id':'flow_edit_portrait','description':'Edit portrait'}]})
        elif path == '/v1/videos/uploads':
            assert json.loads(r.request.post_data)['video'].startswith('data:video/mp4;base64,')
            r.fulfill(json={'media_id':'uploaded-video'})
        elif path == '/v1/chat/completions':
            edits.append(json.loads(r.request.post_data))
            if len(edits) == 3:
                r.fulfill(content_type='text/event-stream', body='data: '+json.dumps({'choices':[{'delta':{'content':'<video src="http://fixture.test/result.mp4" controls></video>'}}]})+'\n\ndata: [DONE]\n\n')
                return
            r.fulfill(content_type='text/event-stream', body='data: '+json.dumps({'error':{'message':'视频音频处理失败', 'code':'speech_edit_failed','upstream_code':'PUBLIC_ERROR_SPEECH_EDIT'}})+'\n\ndata: [DONE]\n\n')
        elif path.startswith('/api/cookie-sync/logs'): r.fulfill(json=[{'created_at':'2026-09-12 00:00:00','account':'fixture@example.com','source':'plugin_api','action':'updated','success':1,'status_code':200,'duration':1,'message':'会话同步成功。'}])
        elif path.startswith('/api/'): r.fulfill(json={})
        elif r.request.url.startswith('https://cdn.tailwindcss.com'): r.continue_()
        else: r.abort()
    page.route('**/*',route)
    page.goto('http://fixture.test/manage')
    page.wait_for_function("document.getElementById('statTotal').textContent === '2'")
    page.reload()
    page.wait_for_function("document.getElementById('statTotal').textContent === '2'")
    assert calls.count('/api/tokens') == 2
    assert page.get_by_text('需要更新 Cookies',exact=True).is_visible()
    assert page.get_by_text('会话暂停',exact=True).is_visible()
    page.locator('#tokenTableBody summary').click()
    assert page.get_by_text('请同步最新 Cookies，错误码：flow_cookies_refresh_required',exact=True).is_visible()
    page.get_by_role('button',name='新增',exact=True).click()
    assert page.locator('#addTokenGoogleCookies').is_visible()
    assert page.locator('#addTokenST').count()==0
    page.get_by_text('如何获取新版 Flow Cookies？').click()
    assert page.get_by_text('在 Chrome 或 Edge 中打开',exact=False).is_visible()
    page.screenshot(path='/tmp/qzent-add-token-ui.png')
    page.evaluate('closeAddModal(); switchTab("settings")')
    page.get_by_role('button',name='随机生成',exact=True).click()
    assert len(page.locator('#cfgNewAPIKey').input_value()) == 64
    assert '/api/admin/apikey' not in calls
    page.goto('http://fixture.test/test')
    page.locator('#apiKey').fill('fixture-test-key')
    page.locator('#baseUrl').fill('http://fixture.test')
    page.evaluate('loadModels()')
    page.locator('[data-model="flow_edit"]').click()
    assert page.locator('#videoEditGroup').is_visible()
    page.locator('#editMediaId').fill('fixture-media')
    page.locator('#editStart').fill('1')
    page.locator('#editEnd').fill('8')
    page.locator('#btnGenerate').click()
    page.wait_for_function("document.getElementById('statusText').textContent === '失败'")
    assert 'PUBLIC_ERROR_SPEECH_EDIT' in page.locator('#outputLog').inner_text()
    assert edits[0]['messages'][0]['content'][-1]['image_url']['url']=='edit://fixture-media?start_frame=30&end_frame=240'
    page.locator('#editMediaId').fill('')
    page.locator('#editVideoFile').set_input_files({'name':'fixture.mp4','mimeType':'video/mp4','buffer':b'fixture-video'})
    page.locator('#btnGenerate').click()
    page.wait_for_function("document.getElementById('editMediaId').value === 'uploaded-video' && document.getElementById('statusText').textContent === '失败'")
    assert edits[1]['messages'][0]['content'][-1]['image_url']['url'].startswith('edit://uploaded-video?')
    page.locator('#btnGenerate').click()
    page.wait_for_function("document.getElementById('statusText').textContent.startsWith('完成')")
    assert page.locator('#outputResult video').count() == 1
    page.locator('#apiKey').fill('')
    page.screenshot(path='/tmp/qzent-video-edit-ui.png')
    assert not errors, errors
    page.goto('http://fixture.test/manage')
    page.locator('#tabCookieSync').click()
    page.wait_for_function("document.getElementById('cookieSyncTableBody').textContent.includes('fixture@example.com')")
    assert page.locator('#panelCookieSync').is_visible()
    assert page.locator('#panelTokens').is_hidden()
    page.locator('#tabTokens').click()
    assert page.locator('#panelCookieSync').is_hidden()
    assert not errors, errors
    browser.close()
    print('Browser smoke passed: automatic load/reload, native token form, tutorial, key generation, mediaId edit, upload edit, upstream error display.')
