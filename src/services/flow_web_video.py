"""Native Flow video RPCs with immutable media version identities."""
import re
from urllib.parse import urlsplit
from uuid import uuid4
from .flow_web import FlowWebError, UUID_RE


def field(value, *path):
    try:
        for index in path:
            value = value[index]
        return value
    except (IndexError, TypeError, KeyError):
        return None


def is_media_record(value):
    # workflowStepId is opaque (CAE, CAI, CAM, ...), not a two-value enum.
    # Identify a media record by its authoritative IDs and metadata shape.
    return (isinstance(value, list) and len(value) > 5
            and all(isinstance(value[i], str) and UUID_RE.fullmatch(value[i]) for i in range(3))
            and isinstance(value[3], str) and bool(value[3])
            and isinstance(value[5], list))


def workflows(value):
    if not isinstance(value, list):
        return []
    if is_media_record(value):
        return [value]
    return [record for child in value for record in workflows(child)]


def public_error_codes(value):
    if isinstance(value, str):
        return re.findall(r'\bPUBLIC_ERROR_[A-Z0-9_]+\b', value)
    if isinstance(value, list):
        return sorted({code for child in value for code in public_error_codes(child)})
    return []


def parse_workflow(record):
    if not is_media_record(record):
        raise FlowWebError('flow_response_invalid', 'Google 返回的视频版本信息不完整', 502)
    url = field(record, 7, 0, 8) or field(record, 7, 4, 2)
    if url:
        parts = urlsplit(url) if isinstance(url, str) else None
        if not parts or parts.scheme != 'https' or parts.hostname != 'flow-content.google' or parts.username or parts.password:
            raise FlowWebError('flow_media_url_invalid', 'Google 返回的视频下载地址无法验证', 502)
    return {'media_id': record[0], 'project_id': record[1], 'tile_id': record[2],
            'status': field(record, 5, 8, 0), 'url': url, 'error_codes': public_error_codes(field(record, 5, 8, 1)),
            'duration': field(record, 7, 1, 2, 0)}


class FlowWebVideo:
    def __init__(self, client):
        self.client = client

    async def get(self, media_id):
        if not isinstance(media_id, str) or not UUID_RE.fullmatch(media_id):
            raise FlowWebError('media_owner_unavailable', '视频版本编号无效，请重新上传原视频')
        record = await self.client.rpc('as29s', [media_id])
        parsed = parse_workflow(record)
        if parsed['media_id'] != media_id:
            raise FlowWebError('flow_response_invalid', 'Google 返回了不匹配的视频版本', 502)
        return record

    async def submit(self, project, prompt, model, aspect, captcha, *, source=None, start_frame=0, end_frame=None, mode="text", references=()):
        context = [None, 22, None, None, None, project, None, None, None, None, [captcha, 1]]
        structured_prompt = [None, None, [[[prompt]]]]
        metadata = [None, None, None, None, str(uuid4()), str(uuid4())]
        refs = [[None, r] for r in references]
        if source is not None:
            original = parse_workflow(source)
            if original['project_id'] != project:
                raise FlowWebError('media_owner_unavailable', '源视频属于其他项目，请使用原账号编辑')
            if type(start_frame) is not int or type(end_frame) is not int or start_frame < 0 or end_frame <= start_frame:
                raise FlowWebError('invalid_edit_range', '视频编辑的起止帧范围无效')
            request = [[None, original['media_id'], start_frame, end_frame], structured_prompt,
                       model, aspect, [None, original['tile_id'], None, None, str(uuid4())]]
            if refs:
                request.extend([None, None, None, refs])
            rpc, batch_type = 'jIps6', 2
        elif mode == 'references' and refs:
            request = [structured_prompt, refs, model, aspect, None, metadata]
            rpc, batch_type = 'MZZa6b', 1
        elif mode == 'start' and len(refs) == 1:
            request = [structured_prompt, model, aspect, None, refs[0], metadata]
            rpc, batch_type = 'eb1hJf', 1
        elif mode == 'start_end' and len(refs) == 2:
            request = [structured_prompt, model, aspect, None, refs[0], refs[1], metadata]
            rpc, batch_type = 'nprQif', 1
        elif mode != 'text' or refs:
            raise FlowWebError('invalid_image_count', '参考图片数量与视频生成方式不匹配')
        else:
            request = [structured_prompt, model, aspect, None, [None, None, None, None, str(uuid4()), str(uuid4())]]
            rpc, batch_type = 'YhhmEf', 1
        # An ambiguous response may have charged credits; do not retry POSTs.
        result = await self.client.rpc(rpc, [[request], context, [str(uuid4()), batch_type]])
        records = workflows(result)
        if len(records) != 1:
            raise FlowWebError('flow_submission_unconfirmed', '无法确认 Google 任务编号，请先在网页查看任务，避免重复扣费', 502)
        parsed = parse_workflow(records[0])
        if parsed['project_id'] != project:
            raise FlowWebError('flow_response_invalid', 'Google 返回了不匹配的项目', 502)
        return parsed
