# Coze 工作流原理与本地落地

## 结论

你当前工作区里真正成型的 Coze 工作流资产是：

- `<本地 Coze 工作流目录>/workflow_7620172153551323136_after_tts.json`
- `<本地 Coze 工作流目录>/rewrite_tts_canvas.json`
- `<本地 Coze 工作流目录>/alltalk_coze_openapi.json`

这套资产已经把链路做到了：

`Start -> RewriteLLM -> AllTalkTTS -> ParseTTSResult -> End`

也就是说，它现在只闭环到了“文案改写 + 配音”，还没有真正进入“视频背景 + BGM + 合成成片”。

## 现有节点分别干什么

1. `Start`
接收输入文案。

2. `RewriteLLM`
把原始中文文案改成更适合短视频口播的版本。

3. `AllTalkTTS`
通过 HTTP 请求调用本地 TTS 服务：
`http://host.docker.internal:7851/api/tts-generate`

4. `ParseTTSResult`
把 TTS 的 JSON 响应解析成工作流输出，比如：
- `output`
- `audio_url`
- `audio_file_path`
- `raw_tts_response`

5. `End`
把上面的字段返回给 Coze。

## Coze 工作流的正确定位

Coze 工作流适合做“编排”，不适合直接做重媒体渲染。

推荐分层是：

- Coze 负责：
  - 接收输入
  - 调 LLM 改写
  - 调 HTTP 插件 / 外部服务
  - 管参数和状态

- 外部服务负责：
  - TTS
  - 图片或视频背景生成
  - BGM 生成或选取
  - ffmpeg 合成

原因很简单：

- 视频生成和音视频混流是重计算任务
- Coze 节点内联代码更适合轻逻辑，不适合做长耗时媒体处理
- 成品输出最好由一个稳定的外部 HTTP 服务统一负责

## 如果要扩成完整链路

推荐改成下面这条：

`Start -> RewriteLLM -> TTS -> VideoBackground -> BGM -> MergeVideo -> End`

更稳的做法是把后三步收敛成一个外部合成服务：

`Start -> RewriteLLM -> TTS -> MediaCompose -> End`

其中 `MediaCompose` 输入：

- `title`
- `rewritten_text`
- `audio_file_path` 或 `audio_url`
- `style`

输出：

- `video_url`
- `video_file_path`
- `cover_url`
- `duration`

这样 Coze 里只维护编排，不把 ffmpeg 细节塞进工作流。

## 本地这次怎么落地

这次我没有继续依赖 Coze 云端节点，而是在仓库里补了一条本地可复现流水线：

- `tools/generate_poem_video.py`

它做的事情是：

1. 接收古诗或文案文本
2. 用 Windows 本机中文语音 `Microsoft Huihui Desktop` 生成配音
3. 用 `ffmpeg` 生成动态渐变背景
4. 用 `ffmpeg` 合成本地 BGM
5. 混音并导出竖屏 MP4 成片

## 为什么这么做

因为当前会话里没有可直接调用的 OpenAI / Sora key，但机器本身具备：

- Windows 中文 TTS
- `ffmpeg`
- Python

所以先把成片闭环做出来，比继续卡在云端依赖上更有价值。

## 后续如果你要回到 Coze

你可以把这个本地脚本再包装成一个本地 HTTP 服务，然后在 Coze 里新增一个 HTTP 节点调用它。这样就能把当前的 TTS 工作流扩成完整视频工作流，而不是只返回音频地址。
