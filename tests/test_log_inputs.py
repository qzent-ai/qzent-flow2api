import io
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from PIL import Image
from src.services.log_inputs import collect_log_inputs, cache_uploaded_video

@pytest.mark.asyncio
async def test_inputs_snapshot_and_source_range(tmp_path):
 image=io.BytesIO();Image.new('RGB',(8,6),'blue').save(image,format='PNG')
 h=SimpleNamespace(file_cache=SimpleNamespace(cache_dir=tmp_path),db=SimpleNamespace(get_media_result_urls=AsyncMock(return_value=['https://example.com/tmp/abc.mp4'])))
 result=await collect_log_inputs(h,[image.getvalue()],{'media_id':'source','start_frame':0,'end_frame':96},None)
 assert result['images'][0]['url'].startswith('/tmp/')
 assert result['images'][0]['width']==8
 assert result['video']=={'media_id':'source','start_frame':0,'end_frame':96,'url':'/tmp/abc.mp4'}
 assert len(list(tmp_path.glob('*.png')))==1

@pytest.mark.asyncio
async def test_unavailable_inputs_do_not_fail_generation(tmp_path):
 h=SimpleNamespace(file_cache=SimpleNamespace(cache_dir=tmp_path),db=SimpleNamespace(get_media_result_urls=AsyncMock(side_effect=RuntimeError('fixture'))))
 r=await collect_log_inputs(h,[b'invalid'],{'media_id':'source','start_frame':0,'end_frame':96},None)
 assert r['images'][0]['unavailable']
 assert r['video']['media_id']=='source' and 'url' not in r['video']

@pytest.mark.asyncio
async def test_uploaded_video_cache_preserves_container(tmp_path):
 h=SimpleNamespace(file_cache=SimpleNamespace(cache_dir=tmp_path))
 url=await cache_uploaded_video(h,b'fixture','video/quicktime')
 assert url.endswith('.mov')
 assert (tmp_path/url.split('/')[-1]).read_bytes()==b'fixture'
