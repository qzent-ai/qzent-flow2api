"""Classify generation logs without changing provider routing or model names."""


def generation_operation(model_config, has_images=False):
    if model_config.get('type') == 'image':
        return 'edit_image' if has_images else 'generate_image'
    video_type = model_config.get('video_type')
    if video_type == 'edit':
        return 'edit_video'
    if video_type == 'extend':
        return 'extend_video'
    return 'generate_video'
