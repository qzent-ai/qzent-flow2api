const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');
test('input previews handle source, ranges, missing history and unsafe URLs',()=>{
 const html=fs.readFileSync('static/manage.html','utf8');const match=html.match(/function renderLogInputs\(request\)\{([\s\S]*?)\n        \}\n/);assert.ok(match);
 const render=vm.runInNewContext('('+match[0]+')',{escapeLogHtml:s=>String(s).replace(/</g,'&lt;'),renderMediaPreview:(label,url)=>label+':'+url});
 assert.match(render({}),/未记录/);
 const result=render({inputs:{images:[{index:1,url:'/tmp/input-a.png'}],video:{media_id:'source',start_frame:0,end_frame:96,url:'/tmp/source.mp4'}}});
 assert.match(result,/参考图片 1/);assert.match(result,/原视频/);assert.match(result,/0.*96/);
 assert.doesNotMatch(render({inputs:{images:[{url:'javascript:alert(1)'}]}}),/javascript:/);
 assert.match(render({inputs:{images:[]}}),/无输入素材/);
});
