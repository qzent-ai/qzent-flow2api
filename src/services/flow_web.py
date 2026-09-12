"""Authenticated flow.google.com RPCs. Never treats Labs ST as Google SSO."""
import json
import re
from typing import Optional
from urllib.parse import urlparse

from curl_cffi.requests import AsyncSession


FLOW_ORIGIN = "https://flow.google.com"
RPC_PATH = "/_/AiSandboxAngularFrontend/data/batchexecute"
COOKIE_DOMAINS = {"google.com", ".google.com", "flow.google.com", ".flow.google.com"}
COOKIE_NAMES = {
    "SID", "HSID", "SSID", "APISID", "SAPISID", "NID", "OSID", "__Secure-OSID",
    "__Secure-1PSID", "__Secure-3PSID", "__Secure-1PAPISID", "__Secure-3PAPISID",
    "SIDCC", "__Secure-1PSIDCC", "__Secure-3PSIDCC", "__Secure-1PSIDTS", "__Secure-3PSIDTS",
}
UUID_RE = re.compile(r"(?:projects/)?([0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12})$", re.I)


class FlowWebError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.status_code = status_code
        super().__init__(f"{message}，错误码：{code}")


def parse_cookies(raw: str) -> list[dict]:
    try:
        items = json.loads(raw)
    except (ValueError, TypeError):
        raise FlowWebError("invalid_google_cookies", "请同步新版 Flow 的 Google Cookie") from None
    if not isinstance(items, list):
        raise FlowWebError("invalid_google_cookies", "Google Cookie 必须包含名称、值和域名")
    result = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("domain") not in COOKIE_DOMAINS or item.get("name") not in COOKIE_NAMES:
            continue
        name, value = item.get("name"), item.get("value")
        if not isinstance(value, str) or any(c in value for c in "\r\n;\x00"):
            raise FlowWebError("invalid_google_cookies", "Google Cookie 格式无效")
        if item.get("path", "/") != "/" or not value:
            continue
        result.append({"name": name, "value": value, "domain": item["domain"], "path": "/", "secure": True})
    if not any(c["name"] in {"SID", "__Secure-1PSID", "__Secure-3PSID"} for c in result):
        raise FlowWebError("flow_session_expired", "未找到 Google 登录会话，请登录 flow.google.com 后重新同步")
    return result


def cookie_header(raw: str) -> str:
    return "; ".join(f"{c['name']}={c['value']}" for c in parse_cookies(raw))


def parse_rpc(text: str, rpc_id: str):
    # Google frames can have byte-count lines and multiple JSON chunks.
    decoder = json.JSONDecoder()
    for line in text.splitlines():
        if not line.lstrip().startswith("["):
            continue
        try:
            frames, _ = decoder.raw_decode(line.lstrip())
        except ValueError:
            continue
        if not isinstance(frames, list):
            continue
        for frame in frames:
            if not isinstance(frame, list) or len(frame) < 3 or frame[1] != rpc_id:
                continue
            if frame[0] == "er":
                if frame[2] == 16:
                    raise FlowWebError("flow_session_expired", "服务器保存的 Google 会话已失效，请先同步浏览器最新 Cookies；浏览器也退出登录时再重新登录", 401)
                raise FlowWebError("flow_rpc_failed", "Google 拒绝了本次操作", 502)
            if frame[0] == "wrb.fr" and frame[2] is None and len(frame) > 5 and isinstance(frame[5], list) and frame[5]:
                upstream = frame[5][0]
                errors = {
                    3: ("flow_invalid_request", "Google 拒绝了请求参数，请检查模型和素材", 400),
                    7: ("flow_permission_denied", "Google 拒绝访问，请检查账号权限或稍后重试", 403),
                    8: ("flow_quota_exceeded", "Google 额度或请求频率受限，请查看账号余额并稍后重试", 429),
                    16: ("flow_session_expired", "Google 会话失效，请同步浏览器最新 Cookies", 401),
                }
                if type(upstream) is int:
                    code, message, status = errors.get(upstream, ("flow_upstream_failed", "Google 处理失败，请稍后重试", 502))
                    raise FlowWebError(code, f"{message}（上游错误码：{upstream}）", status)
            if frame[0] == "wrb.fr" and isinstance(frame[2], str):
                try:
                    return json.loads(frame[2])
                except ValueError:
                    break
    raise FlowWebError("flow_response_invalid", "Google 返回格式不匹配，需检查新版接口兼容性", 502)


class FlowWebClient:
    def __init__(self, google_cookies: str, proxy: Optional[str] = None):
        self.cookies = parse_cookies(google_cookies)
        self._cookie_header = cookie_header(google_cookies)
        # Resolve destination DNS on the SOCKS proxy, as the browser does.
        self.proxy = proxy.replace("socks5://", "socks5h://", 1) if proxy else None
        self.user_agent = None
        self._bootstrap = None
        self._request_id = 100000

    async def _request(self, path: str, *, params=None, data=None) -> str:
        if path not in {"/", RPC_PATH}:
            raise FlowWebError("flow_endpoint_invalid", "不允许的 Flow 接口")
        headers = {"Cookie": self._cookie_header, "Origin": FLOW_ORIGIN, "Referer": FLOW_ORIGIN + "/"}
        if self.user_agent:
            headers["User-Agent"] = self.user_agent
        if data is not None:
            headers.update({"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8", "X-Same-Domain": "1"})
        try:
            async with AsyncSession(trust_env=False) as session:
                response = await session.request(
                    "POST" if data is not None else "GET", FLOW_ORIGIN + path,
                    headers=headers, params=params, data=data, proxy=self.proxy,
                    impersonate="chrome", timeout=180 if params and params.get("rpcids") == "ogiZ0b" else 30, allow_redirects=False,
                )
        except Exception:
            # curl errors may include proxy credentials. Never propagate them.
            raise FlowWebError("flow_connection_failed", "连接新版 Flow 失败，请检查服务器代理", 502) from None
        if response.status_code == 401:
            raise FlowWebError("flow_session_expired", "服务器会话未通过认证，请同步浏览器最新 Cookies", 401)
        if response.status_code == 403:
            raise FlowWebError("flow_access_denied", "Google 拒绝访问，请检查网络或账号访问限制，不能据此认定 Cookies 过期", 403)
        if response.status_code in {301, 302, 303, 307, 308}:
            if urlparse(response.headers.get("Location", "")).hostname == "accounts.google.com":
                raise FlowWebError("flow_cookies_refresh_required", "Google 要求登录，请同步浏览器最新 Cookies；浏览器未登录时请先登录", 401)
            raise FlowWebError("flow_session_unverified", "Flow 返回了未识别的跳转，请稍后重新验证", 502)
        if response.status_code != 200:
            raise FlowWebError("flow_http_error", f"Google 接口返回 HTTP {response.status_code}", 502)
        return response.text

    async def authenticate(self) -> dict:
        text = await self._request("/")
        match = re.search(r"WIZ_global_data\s*=\s*", text)
        try:
            data, _ = json.JSONDecoder().raw_decode(text[match.end():].lstrip()) if match else ({}, 0)
        except ValueError:
            data = {}
        if not isinstance(data, dict) or not data:
            raise FlowWebError("flow_session_unverified", "未能识别 Flow 验证页面，请稍后重试；这不表示 Cookies 已过期", 502)
        email = data.get("oPEP7c")
        if not email and not data.get("SNlM0e"):
            raise FlowWebError("flow_cookies_refresh_required", "服务器未获得登录态，请同步浏览器最新 Cookies；浏览器未登录时请先登录", 401)
        if not isinstance(email, str) or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or not data.get("SNlM0e"):
            raise FlowWebError("flow_session_unverified", "登录账号或验证字段不完整，请重新验证或同步最新 Cookies", 502)
        self._bootstrap = data
        return {"email": email}

    async def rpc(self, name: str, args):
        if self._bootstrap is None:
            await self.authenticate()
        self._request_id += 1
        params = {"rpcids": name, "source-path": "/", "rt": "c", "_reqid": str(self._request_id)}
        for param, key in (("f.sid", "FdrFJe"), ("bl", "cfb2h")):
            if self._bootstrap.get(key):
                params[param] = self._bootstrap[key]
        body = {"f.req": json.dumps([[[name, json.dumps(args, separators=(",", ":")), None, "generic"]]]), "at": self._bootstrap["SNlM0e"]}
        return parse_rpc(await self._request(RPC_PATH, params=params, data=body), name)

    async def create_project(self, title: str) -> str:
        result = await self.rpc("jHPbke", ["projects/*", [None, [title]], [None, 22]])
        # jHPbke returns [project UUID, [title]]. Do not accept a UUID
        # buried in unrelated metadata if Google changes this response schema.
        match = UUID_RE.fullmatch(result[0]) if isinstance(result, list) and result and isinstance(result[0], str) else None
        project_id = match.group(1) if match else None
        if not project_id:
            raise FlowWebError("flow_project_invalid", "Google 未返回新项目 ID", 502)
        return project_id

    async def get_credits(self) -> dict:
        result = await self.rpc("nzlxg", [])
        if not isinstance(result, list) or not result or type(result[0]) is not int or result[0] < 0:
            raise FlowWebError("flow_response_invalid", "Google 余额响应格式异常，请稍后重试", 502)
        tiers = {1: "PAYGATE_TIER_ONE", 2: "PAYGATE_TIER_TWO", 3: "PAYGATE_TIER_NOT_PAID",
                 4: "PAYGATE_TIER_UNSUBSCRIBED_WITH_CREDITS", 5: "PAYGATE_TIER_ZERO",
                 6: "PAYGATE_TIER_EXEMPT", 7: "PAYGATE_TIER_GEMNOVA", 8: "PAYGATE_TIER_TIER1P5"}
        tier = result[1] if len(result) > 1 and type(result[1]) is int else None
        return {"credits": result[0], "userPaygateTier": tiers.get(tier)}

    async def upload_video(self, project: str, data: bytes, content_type: str) -> str:
        from urllib.parse import urlsplit
        if not UUID_RE.fullmatch(project) or content_type not in {'video/mp4', 'video/webm', 'video/quicktime'} or not data:
            raise FlowWebError('invalid_video_upload', '请上传有效的 MP4、WebM 或 MOV 视频')
        if self._bootstrap is None:
            await self.authenticate()
        path = '/upload/v1/flow/upload/video/' + project
        headers = {'Cookie': self._cookie_header, 'Origin': FLOW_ORIGIN, 'Referer': FLOW_ORIGIN + '/',
                   'X-Framework-Xsrf-Token': self._bootstrap['SNlM0e'], 'Slug': 'video.mp4',
                   'X-Goog-Upload-Protocol': 'resumable', 'X-Goog-Upload-Command': 'start',
                   'X-Goog-Upload-Header-Content-Length': str(len(data)),
                   'X-Goog-Upload-Header-Content-Type': content_type}
        try:
            async with AsyncSession(trust_env=False) as session:
                response = await session.post(FLOW_ORIGIN + path, headers=headers, data=b'', proxy=self.proxy,
                                              impersonate='chrome', timeout=60, allow_redirects=False)
                if response.status_code != 200:
                    raise FlowWebError('flow_video_upload_failed', f'Google 视频上传初始化失败（HTTP {response.status_code}）', 502)
                target = response.headers.get('x-goog-upload-url', '')
                parts = urlsplit(target)
                if parts.scheme != 'https' or parts.netloc != 'flow.google.com' or parts.path != path:
                    raise FlowWebError('flow_upload_url_invalid', 'Google 返回的上传地址无法验证', 502)
                headers = {'Cookie': self._cookie_header, 'Origin': FLOW_ORIGIN,
                           'X-Framework-Xsrf-Token': self._bootstrap['SNlM0e'],
                           'X-Goog-Upload-Command': 'upload, finalize', 'X-Goog-Upload-Offset': '0', 'Content-Type': content_type}
                response = await session.post(target, headers=headers, data=data, proxy=self.proxy,
                                              impersonate='chrome', timeout=180, allow_redirects=False)
                if response.status_code != 200:
                    raise FlowWebError('flow_video_upload_failed', f'Google 视频上传失败（HTTP {response.status_code}）', 502)
                result = response.json()
        except FlowWebError:
            raise
        except Exception:
            raise FlowWebError('flow_video_upload_failed', '视频上传连接失败，请稍后重试', 502) from None
        media = result.get('media', {}) if isinstance(result, dict) else {}
        media_id = media.get('name')
        if (media.get('projectId') != project or not isinstance(media_id, str)
                or not UUID_RE.fullmatch(media_id) or result.get('mediaId') != media_id):
            raise FlowWebError('flow_response_invalid', 'Google 未返回有效的视频编号', 502)
        return media_id
