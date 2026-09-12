"""Opt-in check of the actual Docker build context, using synthetic credentials."""
import io
import os
from pathlib import Path
import subprocess
import tarfile
import uuid

import pytest


@pytest.mark.skipif(os.getenv('RUN_DOCKER_CONTEXT_TEST') != '1', reason='requires Docker daemon')
def test_image_context_excludes_local_credentials_and_preserves_license(tmp_path):
    root = Path(__file__).resolve().parents[1]
    (tmp_path / '.dockerignore').write_bytes((root / '.dockerignore').read_bytes())
    files = {
        'LICENSE': 'MIT license fixture',
        'config/setting_example.toml': 'api_key = ""',
        'config/setting.toml': 'SYNTHETIC_PRIVATE_CONFIG',
        'config/setting.toml.bak': 'SYNTHETIC_BACKUP',
        '.worktrees/other/config/setting.toml': 'SYNTHETIC_WORKTREE',
        'browser_data/Default/Cookies': 'SYNTHETIC_COOKIES',
        'browser_data_rt/Default/Cookies': 'SYNTHETIC_COOKIES',
        '.env.production': 'SYNTHETIC_ENV',
        'data/flow.db': 'SYNTHETIC_DATABASE',
        'tmp/result.png': 'SYNTHETIC_MEDIA',
    }
    for name, value in files.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value)
    image = 'qzent-context-test:' + uuid.uuid4().hex
    container = None
    try:
        subprocess.run(['docker', 'build', '-q', '-t', image, '-f', '-', str(tmp_path)],
                       input=b'FROM scratch\nCOPY . /context/\nCMD ["/unused"]\n',
                       capture_output=True, check=True)
        container = subprocess.check_output(['docker', 'create', image]).decode().strip()
        archive = subprocess.check_output(['docker', 'export', container])
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            names = set(tar.getnames())
        included = {name for name in files if 'context/' + name in names}
        assert included == {'LICENSE', 'config/setting_example.toml'}, included
    finally:
        if container:
            subprocess.run(['docker', 'rm', container], capture_output=True)
        subprocess.run(['docker', 'image', 'rm', image], capture_output=True)
