"""T3702 假资质 AI 检测 - ELA/噪点/哈希/EXIF + 过期 + 跨源 + 评分."""
from __future__ import annotations

import hashlib
import io
import logging
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("recruittech.services.ps_detection")

# Expiry/到期阈值
EXPIRY_WARN_DAYS = 30
AUTO_ESCALATE_SCORE = 70


@dataclass
class SuspicionFinding:
    code: str
    severity: int  # 0-100
    detail: str


@dataclass
class VerificationReport:
    target: str  # 文件名 / 营业执照号
    suspicion_score: int  # 0-100
    findings: List[SuspicionFinding] = field(default_factory=list)
    signals: Dict[str, Any] = field(default_factory=dict)
    expiry_warning: Optional[str] = None
    cross_source_mismatches: List[str] = field(default_factory=list)
    auto_escalate: bool = False
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["findings"] = [asdict(f) for f in self.findings]
        return d


# --------- 1) ELA (Error Level Analysis) 启发 ---------

def analyze_ela(image_bytes: bytes) -> Tuple[int, str]:
    """ELA 启发:压缩后差异均值,大差异 = 可能篡改.

    注意:这是启发式,真实场景用 PIL/FFmpeg. 这里用纯 stdlib 模拟.
    """
    if not image_bytes:
        return 50, "empty image bytes"
    # 启发 1: 字节分布熵突变
    n = len(image_bytes)
    sample = image_bytes[: min(n, 4096)]
    entropy = float(len(set(sample))) / 256.0
    # 文件越长、熵越均匀 → 越可能是真扫描件
    base_score = max(0, 50 - int(entropy * 50))
    detail = f"entropy_hint={entropy:.3f} bytes={n}"
    return base_score, detail


# --------- 2) 噪点分析 ---------

def analyze_noise_consistency(image_bytes: bytes) -> Tuple[int, str]:
    """局部噪点不一致 → PS 嫌疑.启发式按数据块离散度."""
    if not image_bytes:
        return 0, "empty"
    block = 512
    samples: List[float] = []
    for i in range(0, len(image_bytes), block):
        chunk = image_bytes[i: i + block]
        if not chunk:
            continue
        # 方差近似 (整数方差)
        m = sum(chunk) / len(chunk)
        var = sum((b - m) ** 2 for b in chunk) / len(chunk)
        samples.append(var)
    if len(samples) < 4:
        return 20, "too few chunks"
    mean = sum(samples) / len(samples)
    variance = sum((s - mean) ** 2 for s in samples) / len(samples)
    # 块间方差高 → 噪点不均匀
    score = min(100, int((variance / (mean + 1)) * 4))
    detail = f"chunk_variance={variance:.1f}"
    return score, detail


# --------- 3) 哈希比对 ---------

def sha256_of(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def hash_compare(image_bytes: bytes, known_hashes: List[str]) -> Tuple[int, str]:
    """如果有匹配 → 0 分; 否则给出风险."""
    if not image_bytes:
        return 0, "empty_bytes"
    h = sha256_of(image_bytes)
    if h in known_hashes:
        return 0, f"matched_known:{h[:10]}"
    return 0, f"no_known_match:{h[:10]}"


# --------- 4) EXIF / 元数据 ---------

def inspect_exif(metadata: Optional[Dict[str, Any]]) -> Tuple[int, str]:
    if not metadata:
        return 30, "no_exif"
    # 矛盾检测
    issues: List[str] = []
    score = 0
    sw = (metadata.get("software") or "").lower()
    if any(s in sw for s in ["photoshop", "gimp", "paint"]):
        issues.append("editor_software")
        score += 60
    creation = metadata.get("creation_date")
    modification = metadata.get("modification_date")
    if creation and modification and modification < creation:
        issues.append("mod_before_creation")
        score += 30

    if not issues:
        score = 5  # 数据齐, 风险低
    return min(score, 100), ",".join(issues) or "clean_exif"


# --------- 5) 过期检测 ---------

CN_DATE_PATTERNS = [
    r"(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})",
    r"(\d{4})(\d{2})(\d{2})",
]


def detect_expiry(expiry_text: Optional[str], now: Optional[datetime] = None) -> Tuple[Optional[str], Optional[datetime]]:
    if not expiry_text:
        return None, None
    now = now or datetime.utcnow()
    # "长期/永久" → 无到期
    if any(t in expiry_text for t in ["长期", "永久", "无固定期限"]):
        return None, None

    m = re.search(CN_DATE_PATTERNS[0], expiry_text)
    if not m:
        m = re.search(CN_DATE_PATTERNS[1], expiry_text)
    if not m:
        return expiry_text, None
    try:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        exp_date = datetime(y, mo, d)
        return expiry_text, exp_date
    except Exception:
        return expiry_text, None


def expiry_warning(expiry_text: Optional[str], now: Optional[datetime] = None) -> Optional[str]:
    """返回告警文案(临期 30 天)."""
    _, exp = detect_expiry(expiry_text, now)
    if not exp:
        return None
    now = now or datetime.utcnow()
    delta = exp - now
    if delta.days < 0:
        return f"营业执照已过期 {-delta.days} 天"
    if delta.days <= EXPIRY_WARN_DAYS:
        return f"营业执照将于 {delta.days} 天后到期"
    return None


# --------- 6) 跨源验证 ---------

def cross_source_validate(sources: Dict[str, str]) -> List[str]:
    """四源: ocr / 工商 / 法人 / 信用代码. 不一致 → 列出 mismatch."""
    if not sources:
        return []
    canonical = (sources.get("ocr") or "").strip()
    mismatches: List[str] = []
    for name, val in sources.items():
        if name == "ocr":
            continue
        if not val:
            continue
        if val.strip() != canonical:
            mismatches.append(f"{name}!={canonical!r}")
    return mismatches


# --------- 主报告 ---------

def build_report(
    target: str,
    image_bytes: bytes = b"",
    metadata: Optional[Dict[str, Any]] = None,
    known_hashes: Optional[List[str]] = None,
    expiry_text: Optional[str] = None,
    sources: Optional[Dict[str, str]] = None,
) -> VerificationReport:
    findings: List[SuspicionFinding] = []
    signals: Dict[str, Any] = {}

    # ELA
    ela_score, ela_detail = analyze_ela(image_bytes)
    signals["ela"] = ela_detail
    if ela_score > 30:
        findings.append(SuspicionFinding("ela_anomaly", ela_score, ela_detail))

    # 噪点
    noise_score, noise_detail = analyze_noise_consistency(image_bytes)
    signals["noise"] = noise_detail
    if noise_score > 30:
        findings.append(SuspicionFinding("noise_inconsistent", noise_score, noise_detail))

    # 哈希
    hash_score, hash_detail = hash_compare(image_bytes, known_hashes or [])
    signals["hash"] = hash_detail
    if hash_detail.startswith("no_known_match"):
        findings.append(SuspicionFinding("hash_unknown", 5, hash_detail))

    # EXIF
    exif_score, exif_detail = inspect_exif(metadata)
    signals["exif"] = exif_detail
    if "editor_software" in exif_detail or "mod_before_creation" in exif_detail:
        findings.append(SuspicionFinding("exif_contradiction", exif_score, exif_detail))

    # 过期
    exp_warn = expiry_warning(expiry_text)

    # 跨源
    mismatches = cross_source_validate(sources or {})
    if mismatches:
        findings.append(SuspicionFinding("cross_source_mismatch", 60, ";".join(mismatches)))

    # 汇总
    total = sum(f.severity for f in findings)
    suspicion = min(100, total)

    if suspicion >= AUTO_ESCALATE_SCORE:
        auto = True
    else:
        auto = False

    if suspicion >= 80:
        summary = "高风险,疑似伪造 → 自动转人工审查"
    elif suspicion >= 50:
        summary = "可疑,建议人工二次复核"
    elif suspicion >= 20:
        summary = "轻度嫌疑,可继续流程但保留审计"
    else:
        summary = "未见明显异常"

    return VerificationReport(
        target=target,
        suspicion_score=suspicion,
        findings=findings,
        signals=signals,
        expiry_warning=exp_warn,
        cross_source_mismatches=mismatches,
        auto_escalate=auto,
        summary=summary,
    )
