"""Connect native Flow media versions to the existing task/cache contract."""
import asyncio
import time
from html import escape
from ..core.config import config
from ..core.models import Task
from .flow_web import FlowWebError
from .flow_web_video import FlowWebVideo, parse_workflow


async def generate_video(handler, token, project, model, prompt, images, stream,
                         generation_result, response_state, request_log_state, edit_directive=None):
    if model.get('video_type') not in {'t2v', 'omni', 'edit', 'i2v', 'r2v'} or model.get('upsample'):
        raise FlowWebError('flow_operation_unsupported', '当前新版接口尚不支持此输入组合，请选择文生视频或无参考图的视频编辑')
    if model.get('video_type') == 'edit' and not edit_directive:
        raise FlowWebError('invalid_edit_source', '视频编辑需要提供原视频编号和编辑帧范围')
    aspect = {'VIDEO_ASPECT_RATIO_LANDSCAPE': 2, 'VIDEO_ASPECT_RATIO_PORTRAIT': 1}.get(model.get('aspect_ratio'))
    if aspect is None:
        raise FlowWebError('invalid_aspect_ratio', '不支持的视频画面比例')
    client = await handler.token_manager.get_flow_web_client(token.google_cookies, token.proxy_url)
    video = FlowWebVideo(client)
    source = await video.get(edit_directive['media_id']) if edit_directive else None
    if source is not None:
        # Ownership is resolved by the handler before this authenticated lookup.
        # An account may have changed its default project since the upload.
        project = parse_workflow(source)['project_id']
    count = len(images or [])
    if count < model.get('min_images', 0) or count > model.get('max_images', 0):
        raise FlowWebError('invalid_image_count', '参考图片数量超出当前模型允许范围')
    references = await upload_references(handler, client, project, images)
    captcha = await solve_captcha(handler, client, project, 'VIDEO_GENERATION')
    mode = 'text'
    model_key = model['model_key']
    if references and model['video_type'] in {'omni', 'r2v'}:
        mode = 'references'
        model_key = model.get('reference_model_key', model_key)
    elif model['video_type'] == 'i2v':
        mode = 'start_end' if count == 2 else 'start'
    kwargs = {'source': source, 'start_frame': edit_directive['start_frame'],
              'end_frame': edit_directive['end_frame']} if edit_directive else {}
    submitted = await video.submit(project, prompt, model_key, aspect, captcha, mode=mode, references=references, **kwargs)
    media_id = submitted['media_id']
    await handler.db.create_task(Task(task_id=media_id, token_id=token.id, model=model['model_key'],
                                      prompt=prompt, status='processing', media_generation_id=media_id))
    await handler._update_request_log_progress(request_log_state, token_id=token.id,
                                               status_text='video_submitted', progress=45,
                                               response_extra={'task_id': media_id})
    try:
        for attempt in range(180):
            current = parse_workflow(await video.get(media_id))
            if current['status'] == 3 and current['url']:
                url = current['url']
                if config.cache_enabled:
                    await handler._update_request_log_progress(request_log_state, token_id=token.id,
                                                               status_text='caching_video', progress=92)
                    try:
                        filename = await handler.file_cache.download_and_cache(url, 'video')
                    except Exception:
                        raise FlowWebError('flow_cache_failed', '视频已生成，但服务器下载失败，请联系管理员检查下载代理', 502) from None
                    url = handler._get_base_url(response_state) + '/tmp/' + filename
                await handler.db.update_task(media_id, status='completed', progress=100,
                                             media_generation_id=media_id, result_urls=[url], completed_at=time.time())
                response_state['url'] = url
                response_state['generated_assets'] = {'type': 'video', 'final_video_url': url,
                    'mediaGenerationId': media_id, 'mediaName': media_id,
                    'aspectRatio': model['aspect_ratio'], 'model': model['model_key'], 'duration': current['duration']}
                handler._mark_generation_succeeded(generation_result)
                if stream:
                    yield handler._create_stream_chunk(f"<video src='{escape(url, quote=True)}' data-media-id='{media_id}' controls style='max-width:100%'></video>", finish_reason='stop')
                else:
                    yield handler._create_completion_response(url, media_type='video', media_id=media_id)
                return
            if current['status'] not in {None, 0, 1, 2, 3, 6}:
                raise FlowWebError((current['error_codes'] or ['flow_generation_failed'])[0], f"Google 视频处理失败（上游状态码：{current['status']}；原始错误码：{', '.join(current['error_codes']) or '未提供'}），请调整素材或描述后重试", 502)
            if stream and attempt % 3 == 0:
                yield handler._create_stream_chunk('视频处理中，请稍候…\n')
            await asyncio.sleep(5)
        raise FlowWebError('flow_generation_timeout', '视频处理超时，请在 Flow 网页查看任务结果，避免重复提交', 504)
    except BaseException:
        await handler.db.update_task(media_id, status='failed', completed_at=time.time())
        raise


async def solve_captcha(handler, client, project, action):
    if config.captcha_method not in {'yescaptcha', 'capmonster', 'ezcaptcha', 'capsolver'}:
        raise FlowWebError('flow_captcha_provider_unsupported', '新版 Flow 请配置支持网页验证码的服务')
    solved = await handler.flow_client._get_api_captcha_token(
        config.captcha_method, project, action=action, proxy_url=client.proxy,
        website_url='https://flow.google.com/project/' + project)
    if not solved or not solved[0]:
        raise FlowWebError('recaptcha_failed', '安全验证失败，请稍后重试或检查验证码服务配置', 502)
    client.user_agent = solved[1]
    return solved[0]


async def upload_references(handler, client, project, images):
    if not images:
        return []
    import io
    from PIL import Image
    from .flow_web_image import FlowWebImage
    result = []
    for data in images or []:
        try:
            with Image.open(io.BytesIO(data)) as image:
                mime = Image.MIME[image.format]
                image.verify()
        except Exception:
            raise FlowWebError('invalid_image_format', '参考图片无法读取，请重新上传 PNG、JPG 或 WebP 图片') from None
        captcha = await solve_captcha(handler, client, project, 'UPLOAD_IMAGE')
        result.append(await FlowWebImage(client).upload(project, data, mime, captcha))
    return result


async def generate_image(handler, token, project, model, prompt, images, stream,
                         generation_result, response_state, request_log_state, edit_directive=None):
    from .flow_web_image import FlowWebImage
    if model.get('upsample'):
        raise FlowWebError('flow_operation_unsupported', '新版 Flow 图片放大尚未适配，请先选择原始分辨率')
    aspect = {'IMAGE_ASPECT_RATIO_LANDSCAPE':3,'IMAGE_ASPECT_RATIO_PORTRAIT':2,
              'IMAGE_ASPECT_RATIO_SQUARE':1,'IMAGE_ASPECT_RATIO_LANDSCAPE_FOUR_THREE':5,
              'IMAGE_ASPECT_RATIO_PORTRAIT_THREE_FOUR':4}.get(model.get('aspect_ratio'))
    if aspect is None:
        raise FlowWebError('invalid_aspect_ratio', '不支持的图片比例')
    client = await handler.token_manager.get_flow_web_client(token.google_cookies, token.proxy_url)
    references = await upload_references(handler, client, project, images)
    captcha = await solve_captcha(handler, client, project, 'IMAGE_GENERATION')
    if stream:
        yield handler._create_stream_chunk('图片生成中，请稍候…\n')
    result = await FlowWebImage(client).generate(project,prompt,model['model_name'],aspect,captcha,references)
    media_id, url = result['media_id'], result['url']
    await handler.db.create_task(Task(task_id=media_id,token_id=token.id,model=model['model_name'],prompt=prompt,status='processing',media_generation_id=media_id))
    try:
        if config.cache_enabled:
            try:
                filename = await handler.file_cache.download_and_cache(url,'image')
            except Exception:
                raise FlowWebError('flow_cache_failed','图片已生成，但服务器下载失败，请联系管理员检查下载代理',502) from None
            url = handler._get_base_url(response_state) + '/tmp/' + filename
        await handler.db.update_task(media_id,status='completed',progress=100,result_urls=[url],completed_at=time.time())
        response_state['url'] = url
        response_state['generated_assets'] = {'type':'image','origin_image_url':url,'final_image_url':url,'mediaGenerationId':media_id}
        handler._mark_generation_succeeded(generation_result)
        if stream:
            yield handler._create_stream_chunk(f'![image]({url})',finish_reason='stop')
        else:
            yield handler._create_completion_response(url,media_type='image')
    except BaseException:
        await handler.db.update_task(media_id,status='failed',completed_at=time.time())
        raise
