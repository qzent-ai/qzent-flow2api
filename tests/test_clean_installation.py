"""Real HTTP startup against empty databases; no Google credentials or calls."""
import os
from pathlib import Path
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import time

import httpx
import pytest


@pytest.mark.skipif(os.getenv('RUN_CLEAN_INSTALL_TEST') != '1', reason='starts isolated HTTP servers')
def test_fresh_install_authentication_random_key_and_restart(tmp_path):
    root = Path(__file__).resolve().parents[1]
    keys = []
    for installation in range(2):
        home = tmp_path / str(installation)
        home.mkdir()
        for folder in ['src', 'static']:
            shutil.copytree(root / folder, home / folder, ignore=shutil.ignore_patterns('__pycache__'))
        (home / 'config').mkdir()
        password = secrets.token_urlsafe(32)
        configuration = (root / 'config/setting_example.toml').read_text()
        configuration = configuration.replace('admin_password = "admin"', f'admin_password = "{password}"')
        config_path = home / 'config/setting.toml'
        config_path.write_text(configuration)
        config_path.chmod(0o600)
        previous = None
        for startup in range(2 if installation == 0 else 1):
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            log_path = home / 'startup.log'
            with log_path.open('ab') as log:
                process = subprocess.Popen(
                    [sys.executable, '-m', 'uvicorn', 'src.main:app', '--host', '127.0.0.1', '--port', str(port)],
                    cwd=home, stdout=log, stderr=log,
                )
                try:
                    with httpx.Client(base_url=f'http://127.0.0.1:{port}', trust_env=False, timeout=5) as client:
                        for _ in range(100):
                            try:
                                if client.get('/health').status_code == 200:
                                    break
                            except httpx.TransportError:
                                pass
                            if process.poll() is not None:
                                raise AssertionError('Fresh server failed to start; private startup log retained')
                            time.sleep(0.1)
                        else:
                            raise AssertionError('Fresh server health timeout')
                        if client.get('/v1/models').status_code != 401:
                            raise AssertionError('Unauthenticated model request must be rejected')
                        response = client.post('/api/admin/login', json={'username': 'admin', 'password': password})
                        if response.status_code != 200:
                            raise AssertionError('Configured admin login failed')
                        response = client.get('/api/tokens')
                        if response.status_code != 200 or response.json() != []:
                            raise AssertionError('Fresh installation must have an empty token pool')
                        with sqlite3.connect(home / 'data/flow.db') as db:
                            key = db.execute('SELECT api_key FROM admin_config LIMIT 1').fetchone()[0]
                        if not key or len(key) < 43 or key == 'han1234':
                            raise AssertionError('Fresh API key is missing or weak')
                        if previous is not None and key != previous:
                            raise AssertionError('API key changed after restart')
                        previous = key
                        if client.get('/v1/models', headers={'Authorization': 'Bearer ' + key}).status_code != 200:
                            raise AssertionError('Generated API key failed authentication')
                        response = client.post('/api/tokens', json={'protocol_mode': 'flow_web', 'google_cookies': 'invalid-json'})
                        if response.status_code != 400:
                            raise AssertionError('Malformed native Cookies must be rejected')
                finally:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
            keys.append(previous)
    if keys[0] != keys[1] or keys[1] == keys[2]:
        raise AssertionError('Restart persistence or independent installation uniqueness failed')
