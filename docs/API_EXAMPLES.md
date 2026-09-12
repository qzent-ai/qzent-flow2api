# API 调用示例

以下示例按本分支实现整理；部署完成并配置可用账号后再执行。请求会消耗上游积分，示例未在本次文档更新中重新进行付费生成验证。

## 地址与认证

将 `FLOW2API_BASE_URL` 设为服务根地址，例如 `http://localhost:38000`（末尾不带 `/v1`）。通过本地环境变量提供 `FLOW2API_API_KEY`，值从管理页获取，不使用管理员密码或插件连接 Token。

OpenAI 客户端的 Base URL 则应填写 `http://localhost:38000/v1`。本服务适配媒体生成接口，不代表兼容所有聊天模型、工具调用或 OpenAI 端点。

## OpenAI 兼容调用

将下面任一 JSON 示例保存为 `request.json`，替换图片占位符后执行：

```bash
curl -N "$FLOW2API_BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $FLOW2API_API_KEY" \
  -H 'Content-Type: application/json' \
  --data-binary @request.json
```

示例使用 `stream: true`，`curl -N` 便于及时显示流式内容。也可设置 `stream: false` 等待完整响应。视频耗时较长，应相应调整客户端和反向代理超时。

### 文生图

```json
{
  "model": "gemini-3.1-flash-image-landscape",
  "messages": [
    {
      "role": "user",
      "content": "山间木屋，清晨薄雾，水彩风格"
    }
  ],
  "stream": true
}
```

### 参考图编辑

```json
{
  "model": "gemini-3.1-flash-image-landscape",
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "把背景改为雪景，保留主体"
        },
        {
          "type": "image_url",
          "image_url": {
            "url": "data:image/png;base64,<参考图的纯Base64内容>"
          }
        }
      ]
    }
  ],
  "stream": true
}
```

### 文生视频

```json
{
  "model": "veo_3_1_t2v_fast_landscape",
  "messages": [
    {
      "role": "user",
      "content": "镜头缓慢接近山间木屋，晨雾轻轻流动"
    }
  ],
  "stream": true
}
```

### 首尾帧视频

```json
{
  "model": "veo_3_1_i2v_s_fast_fl",
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "从清晨平滑过渡到黄昏"
        },
        {
          "type": "image_url",
          "image_url": {
            "url": "data:image/png;base64,<首帧Base64>"
          }
        },
        {
          "type": "image_url",
          "image_url": {
            "url": "data:image/png;base64,<尾帧Base64>"
          }
        }
      ]
    }
  ],
  "stream": true
}
```

### 参考图视频

```json
{
  "model": "veo_3_1_r2v_fast_portrait",
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "参考图片中的建筑，生成缓慢推进的镜头"
        },
        {
          "type": "image_url",
          "image_url": {
            "url": "data:image/png;base64,<参考图Base64>"
          }
        }
      ]
    }
  ],
  "stream": true
}
```

### 视频编辑

```json
{
  "model": "flow_edit",
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "将建筑外墙改为白色，保留镜头运动"
        },
        {
          "type": "image_url",
          "image_url": {
            "url": "edit://<media_id>?start_frame=0&end_frame=120"
          }
        }
      ]
    }
  ],
  "stream": true
}
```

图片 MIME 类型须与实际文件一致；Data URL 中 `base64` 后是逗号。首尾帧示例移除第二张图片后可作首帧视频；所列 R2V 模型最多接收 3 张参考图，其他模型以各自限制为准。

视频编辑中的 `<media_id>` 必须替换为生成或上传返回的原始编号。编辑范围按 30 fps 计算，上例为前 4 秒，不能超过源视频范围；素材所属账号必须仍可用。

## Gemini 格式文生图

将以下请求保存为 `gemini-request.json`：

```json
{
  "contents": [{"role": "user", "parts": [{"text": "山间木屋，清晨薄雾，水彩风格"}]}]
}
```

```bash
curl "$FLOW2API_BASE_URL/v1beta/models/gemini-3.1-flash-image-landscape:generateContent" \
  -H "x-goog-api-key: $FLOW2API_API_KEY" \
  -H 'Content-Type: application/json' \
  --data-binary @gemini-request.json
```

如需流式输出，将方法改为 `:streamGenerateContent?alt=sse` 并给 curl 添加 `-N`。Gemini 图片输入可使用 `contents[].parts[].inlineData`，包含 `mimeType` 和纯 Base64 `data`，不加 Data URL 前缀。

## 结果与错误

OpenAI 与 Gemini 响应结构不同，应按所选接口解析。保留生成结果的 `media_id` 供后续编辑使用，并及时下载需要长期保存的媒体，缓存链接可能过期。

失败时保留完整错误结构中的中文说明、本地错误码及可用的上游原始错误码。流式调用还需检查事件内容，不能只凭最初的 HTTP 200 判断生成成功。
