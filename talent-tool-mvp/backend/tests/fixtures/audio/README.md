# Audio Fixtures for STT Tests

This directory holds synthetic / real audio samples for STT (speech-to-text) tests.

## Files

| File | Language | Duration | Purpose |
| --- | --- | --- | --- |
| `sample_zh_001.wav` | zh (中文) | ~3s | 中文转写验证 |
| `sample_en_001.wav` | en (English) | ~3s | 英文转写验证 |
| `sample_ja_001.wav` | ja (日本語) | ~3s | 日文转写验证 |
| `sample_short_mono_16k.wav` | n/a | ~1s | 端到端 pipeline smoke test |
| `sample_long_60s.wav` | zh | ~60s | 长音频分片 + aliyun_stt fallback 链路 |

## Generation

测试启动时会自动校验:
1. 文件存在 (`pytest -m real_api backend/providers/stt/tests/test_whisper_real.py`)
2. 大小 > 1KB (避免空文件被 upstream 拒绝)
3. RIFF/WAV header 有效

缺失时,`generate_audio_fixtures.py` 脚本会用 `numpy + scipy` 生成正弦波合成 WAV,
并在 README 顶部标注 `SYNTHETIC — not for transcription accuracy`。

## Real Audio

如需真实人声样本,可以从以下公共来源下载:
- Common Voice (Mozilla): https://commonvoice.mozilla.org/
- LibriSpeech (English): http://www.openslr.org/12/
- AISHELL-1 (中文): https://www.openslr.org/33/

下载后放到本目录,文件名保持 `sample_<lang>_NNN.wav` 即可。