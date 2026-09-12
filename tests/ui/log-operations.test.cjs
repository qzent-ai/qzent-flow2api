const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
test('generation and edit log summaries have distinct operation labels',()=>{
 const html=fs.readFileSync('static/manage.html','utf8');
 const source=html.match(/getLogOperationLabel=(.*),\n/)[1];
 const label=vm.runInNewContext('('+source+')');
 for(const [operation,expected] of Object.entries({generate_video:'视频生成',edit_video:'视频编辑',generate_image:'图片生成',edit_image:'图片编辑',extend_video:'视频续写'}))assert.equal(label({operation}),expected);
 assert.equal(label({operation:'unknown'}),'');
});
