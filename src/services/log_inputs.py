"""Best-effort cached input previews; never store raw media in request logs."""
import asyncio
import io
import re
import uuid
from urllib.parse import urlsplit
from PIL import Image


def _image_preview(directory, data):
    with Image.open(io.BytesIO(data)) as image:
        width, height = image.size
        image.thumbnail((1280, 1280))
        image = image.convert('RGB')
        filename = f'input-{uuid.uuid4().hex}.png'
        image.save(directory / filename, format='PNG')
    return {'url': '/tmp/' + filename, 'width': width, 'height': height}


async def cache_uploaded_video(handler, data, content_type):
    extension = {'video/mp4': '.mp4', 'video/quicktime': '.mov', 'video/webm': '.webm', 'video/x-msvideo': '.avi', 'video/3gpp': '.3gp', 'video/x-m4v': '.m4v'}.get(content_type, '.mp4')
    filename = f'input-{uuid.uuid4().hex}{extension}'
    try:
        await asyncio.to_thread((handler.file_cache.cache_dir / filename).write_bytes, data)
        return '/tmp/' + filename
    except Exception:
        return None


async def collect_log_inputs(handler, images, edit_directive, video_media_id):
    result = {'images': []}
    for index, data in enumerate(images or []):
        try:
            preview = await asyncio.to_thread(_image_preview, handler.file_cache.cache_dir, data)
        except Exception:
            preview = {'unavailable': True}
        result['images'].append({'index': index + 1, **preview})
    source = (edit_directive or {}).get('media_id') or video_media_id
    if source:
        video = {'media_id': source}
        if edit_directive:
            video.update({key: edit_directive.get(key) for key in ('start_frame', 'end_frame')})
        try:
            urls = await handler.db.get_media_result_urls(source)
            for url in urls:
                path = urlsplit(url).path
                if re.fullmatch(r'/tmp/[a-zA-Z0-9_-]+\.(mp4|mov|webm|avi|3gp|m4v)', path):
                    video['url'] = path
                    break
        except Exception:
            pass
        result['video'] = video
    return result
