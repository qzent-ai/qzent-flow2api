"""Image RPCs observed on the migrated Flow frontend."""
import base64
import secrets
from uuid import uuid4
from urllib.parse import urlsplit
from .flow_web import FlowWebError, UUID_RE
from .flow_web_video import field, workflows, parse_workflow


def context(project, captcha):
    return [None,22,None,None,None,project,None,None,None,None,[captcha,1]]


class FlowWebImage:
    def __init__(self, client):
        self.client = client

    async def upload(self, project, data, mime, captcha):
        if mime not in {'image/png', 'image/jpeg', 'image/webp'}:
            raise FlowWebError('invalid_image_format', '请使用 PNG、JPG 或 WebP 图片')
        result = await self.client.rpc('maseQ', [context(project,captcha),base64.b64encode(data).decode(),mime,True,None,None,None,False,'reference'])
        records = workflows(result)
        if len(records) != 1 or parse_workflow(records[0])['project_id'] != project:
            raise FlowWebError('flow_image_upload_failed', 'Google 未返回有效的参考图片编号', 502)
        return records[0][0]

    async def generate(self, project, prompt, model, aspect, captcha, references=()):
        ctx = context(project,captcha)
        request = [None,None,[[r,None,None,None,1] for r in references] or None,
                   secrets.randbelow(2**31),aspect,model,None,ctx,[[[prompt]]],None,None,None,str(uuid4()),str(uuid4())]
        result = await self.client.rpc('ogiZ0b',[None,[request],1,ctx,[str(uuid4())]])
        record = field(result,0,0)
        media_id = field(record,0)
        url = field(record,6,0,13)
        gallery_project = field(result,1,0,4)
        if not isinstance(media_id,str) or not UUID_RE.fullmatch(media_id) or gallery_project != project:
            raise FlowWebError('flow_response_invalid','Google 未返回有效的图片结果',502)
        parts = urlsplit(url) if isinstance(url,str) else None
        if not parts or parts.scheme != 'https' or parts.netloc != 'flow-content.google':
            raise FlowWebError('flow_media_url_invalid','Google 返回的图片下载地址无法验证',502)
        return {'media_id':media_id,'url':url}
