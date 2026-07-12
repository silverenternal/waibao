"""生成 STT 测试用的合成音频 fixture.

5 个 WAV 文件:
    - sample_zh_001.wav       (中文, ~3s)
    - sample_en_001.wav       (English, ~3s)
    - sample_ja_001.wav       (Japanese, ~3s)
    - sample_short_mono_16k.wav (~1s, 用于 pipeline smoke test)
    - sample_long_60s.wav     (中文, ~60s, 用于长音频 fallback 链路)

依赖: pip install numpy
输出: <backend>/tests/fixtures/audio/sample_*.wav
"""
from __future__ import annotations

import math
import struct
import sys
import wave
from pathlib import Path

OUT = Path(__file__).resolve().parent

SAMPLE_RATE = 16000


def _synth_wav(
    path: Path,
    *,
    duration_sec: float,
    base_freq: float = 440.0,
    harmonics: tuple[float, ...] = (1.0, 0.5, 0.25),
) -> None:
    """合成多谐波正弦波 + 静音段,作为占位音频."""
    total_samples = int(duration_sec * SAMPLE_RATE)
    frames = bytearray()
    for i in range(total_samples):
        t = i / SAMPLE_RATE
        # 振幅包络: 0.1s fade in + 0.1s fade out
        env = 1.0
        if t < 0.1:
            env = t / 0.1
        elif t > duration_sec - 0.1:
            env = max(0.0, (duration_sec - t) / 0.1)
        sample = 0.0
        for h_idx, h_amp in enumerate(harmonics, start=1):
            sample += h_amp * math.sin(2 * math.pi * base_freq * h_idx * t)
        sample = sample / sum(harmonics) * 0.6 * env
        # int16
        frames.extend(struct.pack("<h", int(sample * 32767)))

    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(bytes(frames))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    # 中文 — 基频 220Hz (低)
    _synth_wav(OUT / "sample_zh_001.wav", duration_sec=3.0, base_freq=220.0)
    # 英文 — 基频 440Hz (中)
    _synth_wav(OUT / "sample_en_001.wav", duration_sec=3.0, base_freq=440.0)
    # 日文 — 基频 660Hz (高)
    _synth_wav(OUT / "sample_ja_001.wav", duration_sec=3.0, base_freq=660.0)
    # 短 — 1s 用于 smoke test
    _synth_wav(OUT / "sample_short_mono_16k.wav", duration_sec=1.0, base_freq=523.0)
    # 长 — 60s 用于长音频链路
    _synth_wav(OUT / "sample_long_60s.wav", duration_sec=60.0, base_freq=196.0)
    print(f"生成 5 个 WAV 样本到 {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())