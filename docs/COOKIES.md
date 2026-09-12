# 新版 Flow Cookie 获取与导入

适用于普通 Chrome / Edge 浏览器，不需要 AdsPower。

1. 打开 `https://flow.google.com/`，手动登录自己的 Google 账号，确认能够进入 Flow 项目。
2. 使用支持 **JSON 导出**的 Cookie 扩展。在当前 Flow 页面选择导出 JSON，不要选择 Header、文本或 Netscape 格式。管理页“新增”中的教程提供 Cookie-Editor 官网入口。
3. 导出内容应是数组，每条记录至少包含 `name`、`value`、`domain`。应包含适用于当前 Flow 页面的 `.google.com` 和 Flow 域名 Cookie；不要只复制旧版 `labs.google` 的 session-token，也不要导出其他网站的数据。
4. 在 Qzent Flow2API 管理页点击“新增”，把完整 JSON 粘贴到“Google Cookies”，按需填写备注和代理，再添加。
5. 检查账号、会话状态；确认账号正确后，再配置验证码服务并运行一次生成测试。

格式示意（不能用作实际凭据）：

```json
[
  {"name": "COOKIE_NAME", "value": "YOUR_COOKIE_VALUE", "domain": ".google.com", "path": "/", "secure": true}
]
```

只用 `document.cookie` 不能取得 HttpOnly Cookie，不能用它代替完整导出。不要把 Cookie JSON、截图中的凭据或数据库上传到公开 Issue；Cookie 相当于登录凭据。粘贴后清理剪贴板及临时导出文件。

## 同步与排错

| 提示或状态 | 处理方式 |
|---|---|
| JSON 格式错误 | 重新选择 JSON 导出，复制完整数组，保留域名字段 |
| 需要更新 Cookies / `flow_session_expired` / `flow_cookies_refresh_required` | 在 Flow 中确认登录，重新导出并更新；必要时先重新登录 |
| 账号不匹配 / `flow_account_mismatch` | 确认当前浏览器账号与要更新的账号一致，避免把另一个账号的 Cookie 写入 |
| 连接失败 | 检查服务器网络和该账号的代理；连接失败不等于已经确认登录失效 |
| Cookie 已同步，但生成失败 | 查看生成错误码、账号积分、验证码服务和媒体下载网络；同步成功只说明同步请求成功 |
| 插件同步接口 401 | 检查插件的连接地址和连接 Token；不要填 API Key 或 Google Cookie |
| 插件 `Failed to fetch` | 请求可能没有到达服务器；检查地址、HTTPS、浏览器网络权限和代理，并查看插件日志 |

新版 Cookie 会随 Google 登录状态和浏览器访问变化。使用适配版同步插件时，浏览器关闭期间无法继续同步。服务端“Cookie 同步日志”仅记录已到达接口的请求。
