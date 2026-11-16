# 语音提问与朗读

日期：2026-11-16。只做在聊天页。朗读和识别都走阿里云百炼，密钥留在后端的 `DASHSCOPE_API_KEY`，临时音频链接不交给浏览器，音频也不写入数据库。页面上没有 English / 中文开关。

## 朗读

模型是 `qwen3-tts-flash`，音色 `Cherry`，`language_type` 为 `Auto`。中文和英文由模型按片段发音。地址从 `DASHSCOPE_BASE_URL` 推出，请求发到 `/api/v1/services/aigc/multimodal-generation/generation`。后端下载返回的音频，再以 `audio/wav` 交给页面。百炼有时把 WAV 的数据长度写成 `0x7FFFFFFF`，读取时按文件里实际剩下的字节计算。

页面先去掉 Markdown 和 `[S1]` 这种引用，再按句切开。句号、问号、感叹号、中文句末标点和换行都算一句；数字后面的小数点不算。第一句一出现就请求 `POST /api/speech/synthesize`。后面的句子在上一句播放时继续合成，一次最多拼到约 480 字。单句超过 600 字时，后端再按句切开，拼成一段 WAV 后返回。朗读用的 HTTP 连接会复用。

Read answers 记在 `localStorage` 的 `coursemate.speech.speak`，默认关闭。打开后，回答写到第一句就开始读，回答失败则停。每条已完成的回答都有 Replay，不看这个开关。开始识别、发送、打开别的聊天、重播另一条、关闭朗读开关或离开聊天页时，立刻停掉播放和还没返回的合成请求。

## 麦克风

模型是 `qwen3-asr-flash-realtime`，地址是 `/api-ws/v1/realtime`。会话不设置 language，以便中英混说。格式是 16 kHz、16-bit PCM。浏览器采集后转成这个格式，在 WebSocket 连上之前先把音频留在内存里，连上再发出，避免丢掉开头。开发环境的 `/api` 代理打开了 WebSocket 转发。

页面发给后端的是 `{type:"audio", pcm}` 和 `{type:"stop"}`。后端转成 `input_audio_buffer.append`，并在停止时发送 `session.finish`。识别结果里，已确认文字加正在识别的片段作为临时字幕，整段替换输入框；`completed` 的 `transcript` 作为最终文字。没有文字或识别失败时，恢复说话前的草稿。服务端用静音约 1.2 秒判断一句结束，单次最长约 60 秒。连接还没建立时再点一次，直接恢复草稿，不显示失败。

## 核对

自动测试不调用百炼。`backend/tests/test_speech.py` 共 9 项通过，覆盖了这些点：合成请求使用 Auto 和 Cherry、超长文本按句切开、临时字幕是已确认文字加正在识别的片段、识别会话不设置 language、占位 WAV 长度仍能拼起来、合成接口返回 `audio/wav`。

在 Chrome 里打开 `http://127.0.0.1:5173/chat`：

- English / 中文开关不在。Read answers、Mic 和 Replay 还在。
- 两句回答的 Replay 会先合成第一句并开始播放，第二句的请求在播放后返回。
- 打开 Read answers 后发送 “What is f(n) in one sentence?”，回答约 0.8 秒写完，合成在回答结束后马上发出，约 2 秒返回。
- 点 Mic 后按钮变成 Stop，再点一次回到 Mic，没有出现 “Voice recognition failed.”。连接还没建立时停止也是这样。这次没有对着麦克风说话，所以没有核对逐字出现的句子。

## 界限

第一句仍要等百炼生成这一句的音频，通常一两秒，页面没有改成流式朗读。没有麦克风的浏览器里 Mic 会禁用。识别和朗读都需要后端在线，并且百炼密钥有额度。每次识别结束后，到百炼的连接可能还会留着；下一次识别可以照常开始。
