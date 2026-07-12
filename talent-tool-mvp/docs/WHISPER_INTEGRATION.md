# OpenAI Whisper + aliyun_stt 集成文档 (T1102)

waibao STT 链路默认走 **OpenAI Whisper**,配额耗尽 / 失败时降级到 **阿里云一句话识别**。

---

## 1. 申请 OpenAI API key

### 1.1 步骤

1. 访问 [OpenAI Platform](https://platform.openai.com/)
2. 注册账号 → 「API keys」 → 「Create new secret key」
3. 复制 `sk-...` 形式的 key (创建后只显示一次)
4. 在「Billing」充值 — Whisper 按分钟计费 (¥0.006/分钟,2026 年 7 月价格)

### 1.2 配额

| 模型 | 价格 | RPM | TPM |
| --- | --- | --- | --- |
| whisper-1 | $0.006 / minute | 50 (Tier 1) | 不限 |

### 1.3 限流策略

- 单 org: 50 req/min (Tier 1), 5 req/s 瞬时
- 429 响应: 等待 20s 后重试
- 长音频 > 25MB: 走分段上传 (代码已自动处理)

### 1.4 配置

```bash
export OPENAI_API_KEY="sk-..."
# 可选: 自定义 base_url (用于 Azure OpenAI / 中转代理)
export OPENAI_BASE_URL="https://api.openai.com/v1"
```

---

## 2. 音频格式要求

### 2.1 支持的格式

Whisper API 接受:
- `mp3`, `mp4`, `mpeg`, `mpga`, `m4a`, `wav`, `webm`
- 最大文件大小: **25 MB** (超出需分段)

### 2.2 推荐参数

| 字段 | 推荐值 | 说明 |
| --- | --- | --- |
| sample_rate | 16000 Hz | 与训练数据一致 |
| channels | 1 (mono) | 节省带宽 |
| bit_depth | 16-bit PCM | wav 容器 |
| duration | < 60s/段 | 长音频分段 |

### 2.3 audio fixture 生成

仓库自带合成 WAV 工具:

```bash
cd backend/tests/fixtures/audio
python3 generate_audio_fixtures.py
```

生成 5 个样本 (中文/英文/日文/短/长),均为 16kHz mono 16-bit PCM。

如需真实人声样本 (提高识别准确率测试):
- [Mozilla Common Voice](https://commonvoice.mozilla.org/) — 多语种众包
- [LibriSpeech](http://www.openslr.org/12/) — 英文有声书
- [AISHELL-1](https://www.openslr.org/33/) — 中文普通话

下载后保持 `sample_<lang>_NNN.wav` 命名即可。

---

## 3. 降级链路: aliyun_stt

### 3.1 申请步骤

1. 访问 [阿里云智能语音交互](https://nls-portal.console.aliyun.com/)
2. 开通「一句话识别」服务
3. 创建项目 → 获取 `APP_KEY`
4. 在 RAM 控制台创建 AccessKey (id + secret)

### 3.2 配额

| 套餐 | 月配额 | 价格 |
| --- | --- | --- |
| 试用版 | 2,000 次 | 免费 (新用户) |
| 商用版 | 起步 100 万次 | ¥0.0004/次 |

### 3.3 配置

```bash
export ALIYUN_ACCESS_KEY_ID="..."
export ALIYUN_ACCESS_KEY_SECRET="..."
export ALIYUN_ASR_APP_KEY="..."
```

### 3.4 触发降级的场景

代码中 `whisper_provider.transcribe()` 抛以下异常时,服务层应 fallback 到 aliyun:
- `AuthError` (401) — key 失效
- `QuotaExceededError` (429, OpenAI 用 RateLimitError 包装)
- `UpstreamUnavailableError` (5xx)
- `InvalidRequestError` (400, 通常是音频格式问题 — fallback 不一定能修好)

---

## 4. 测试运行

### 4.1 Whisper 真实测试

```bash
cd backend
export OPENAI_API_KEY="sk-..."
pytest -m real_api providers/stt/tests/test_whisper_real.py -v
```

测试矩阵:
- 中文 / 英文 / 日文 三语种
- 自动语言检测 (language='auto')
- 短音频 smoke test (1s)
- 长音频降级链路 (60s → aliyun)
- 配额监控 (5 次连续调用平均延迟)

### 4.2 Whisper + aliyun 双链路测试

```bash
export OPENAI_API_KEY="sk-..."
export ALIYUN_ACCESS_KEY_ID="..."
export ALIYUN_ACCESS_KEY_SECRET="..."
export ALIYUN_ASR_APP_KEY="..."
pytest -m real_api providers/stt/tests/test_whisper_real.py::test_long_audio_falls_back_to_aliyun -v
```

---

## 5. 性能调优

| 场景 | 优化 |
| --- | --- |
| 长音频 (>25MB) | 提前用 ffmpeg 切片到 ≤60s 段, 并发转写 |
| 高并发 | 加本地队列 (asyncio.Queue), 控制并发 ≤ 5 |
| 降低成本 | 短音频用 aliyun_stt (¥0.0004/次), 长音频走 Whisper |
| 离线 / 私有化 | whisper.cpp 本地部署, 替换 WhisperProvider |

---

## 6. 故障排查

| 错误 | 原因 | 解决 |
| --- | --- | --- |
| `401 Incorrect API key` | key 失效 | 重新生成 |
| `429 Rate limit reached` | 配额 / RPM 超限 | 降级 aliyun_stt |
| `400 Invalid file format` | 音频编码不支持 | 用 ffmpeg 转 wav/mp3 |
| `whisper.transcribe` 超时 (默认 8s) | 文件太大 / 网络慢 | 调大 `httpx.Timeout(60.0)` |
| 识别结果为空 | 合成音频无语音内容 | 用真实人声样本 |

---

## 7. 安全建议

1. **OPENAI_API_KEY 必须用 secret manager** — 不能提交到 git
2. **音频含 PII** — 上传前做去标识化 (删除人名/电话), 或用本地 whisper
3. **跨境合规** — OpenAI API 数据出境, 需用户授权 + 隐私协议
4. **审计日志** — 记录每次转写的 `audio_hash` + `result_text` 前 200 字, 留痕