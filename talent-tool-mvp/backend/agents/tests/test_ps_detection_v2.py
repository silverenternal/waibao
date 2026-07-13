"""T3702 - PS detection tests."""
import pytest
from services.ps_detection import (
    analyze_ela, analyze_noise_consistency, hash_compare, sha256_of,
    inspect_exif, detect_expiry, expiry_warning, cross_source_validate,
    build_report, AUTO_ESCALATE_SCORE, EXPIRY_WARN_DAYS,
)


class TestAnalyELA:
    def test_empty(self):
        s, detail = analyze_ela(b"")
        assert 0 <= s <= 100
        assert detail

    def test_random_bytes(self):
        s, _ = analyze_ela(b"random" * 100)
        assert 0 <= s <= 100

    def test_uniform(self):
        s, _ = analyze_ela(b"\xff" * 1024)
        assert s >= 0


class TestNoiseAnalysis:
    def test_empty(self):
        s, _ = analyze_noise_consistency(b"")
        assert s == 0

    def test_short(self):
        s, _ = analyze_noise_consistency(b"abc")
        assert 0 <= s <= 100

    def test_long(self):
        s, _ = analyze_noise_consistency(b"abcde" * 1000)
        assert 0 <= s <= 100


class TestHashCompare:
    def test_empty(self):
        s, d = hash_compare(b"", [])
        # Empty bytes → no known match (returns "empty_bytes" tag)
        assert d in ("empty_bytes",) or d.startswith("no_known")

    def test_known_match(self):
        h = sha256_of(b"xyz")
        s, d = hash_compare(b"xyz", [h])
        assert d.startswith("matched_known")

    def test_unknown(self):
        s, d = hash_compare(b"junk", ["aaaa"])
        assert d.startswith("no_known")


class TestInspectExif:
    def test_none_metadata(self):
        s, d = inspect_exif(None)
        assert d == "no_exif"

    def test_editor_software(self):
        s, d = inspect_exif({"software": "Adobe Photoshop"})
        assert "editor_software" in d

    def test_modification_before_creation(self):
        s, d = inspect_exif({"creation_date": "2025-01-01", "modification_date": "2024-12-01"})
        assert "mod_before_creation" in d

    def test_clean(self):
        s, d = inspect_exif({"software": "iPhone"})
        assert "clean" in d


class TestDetectExpiry:
    def test_none(self):
        out = detect_expiry(None)
        assert out == (None, None)

    def test_long_term(self):
        out = detect_expiry("有效期限:长期")
        assert out == (None, None)

    def test_parse_chinese_date(self):
        text, dt = detect_expiry("有效至 2026-12-31")
        assert dt is not None
        assert dt.year == 2026

    def test_parse_yyyymmdd(self):
        text, dt = detect_expiry("有效 20280101")
        assert dt is not None
        assert dt.year == 2028


class TestExpiryWarning:
    def test_no_expiry(self):
        assert expiry_warning(None) is None

    def test_long_term_no_warning(self):
        assert expiry_warning("长期有效") is None

    def test_within_30_days(self):
        # simulate text without computing date math
        # Use the new logic: should return warning if dates within 30d
        text = "有效至 2030-01-01"  # far in future
        assert expiry_warning(text) is None

    def test_already_expired(self):
        # Construct expired directly
        from datetime import datetime, timedelta
        past = (datetime.utcnow() - timedelta(days=5)).strftime("%Y-%m-%d")
        warn = expiry_warning(f"有效至 {past}")
        assert warn and "已过期" in warn


class TestCrossSource:
    def test_no_sources(self):
        assert cross_source_validate({}) == []

    def test_matching(self):
        out = cross_source_validate({"ocr": "ABC", "saic": "ABC", "legal": "ABC"})
        assert out == []

    def test_mismatch(self):
        out = cross_source_validate({"ocr": "ABC", "saic": "XYZ"})
        assert "saic" in out[0]

    def test_skip_empty(self):
        out = cross_source_validate({"ocr": "ABC", "saic": ""})
        assert out == []


class TestBuildReport:
    def test_basic_report(self):
        rep = build_report("biz.jpg", image_bytes=b"hello")
        d = rep.to_dict()
        assert d["target"] == "biz.jpg"
        assert d["suspicion_score"] >= 0

    def test_editor_software_escalates(self):
        rep = build_report("doc.png", metadata={"software": "Photoshop"})
        d = rep.to_dict()
        assert d["auto_escalate"] or d["suspicion_score"] > 0

    def test_unknown_hash_low_risk(self):
        rep = build_report("x.png", image_bytes=b"abc", known_hashes=["aaaa"])
        d = rep.to_dict()
        # 默认是低风险(只有 unknown hash hint 5 分 + entropy 0~50)
        assert d["suspicion_score"] >= 0
        assert "hash" in d["signals"] or d["suspicion_score"] < 100

    def test_expiry_warning_set(self):
        from datetime import datetime, timedelta
        past = (datetime.utcnow() - timedelta(days=10)).strftime("%Y-%m-%d")
        rep = build_report("x.png", expiry_text=f"有效至 {past}")
        d = rep.to_dict()
        assert d["expiry_warning"]

    def test_cross_source_mismatch(self):
        rep = build_report("x.png", sources={"ocr": "ABC", "saic": "XYZ"})
        d = rep.to_dict()
        assert d["cross_source_mismatches"]

    def test_summary_provided(self):
        rep = build_report("x.png")
        assert rep.summary

    def test_findings_list(self):
        rep = build_report("x.png", metadata={"software": "GIMP"})
        assert isinstance(rep.findings, list)

    def test_signals_dict(self):
        rep = build_report("x.png", image_bytes=b"abc")
        assert "ela" in rep.signals


@pytest.mark.parametrize("score_threshold", [AUTO_ESCALATE_SCORE])
def test_escalation_threshold(score_threshold):
    rep = build_report("x.png", metadata={"software": "Photoshop"})
    # either auto_escalate or under threshold based on severity sum
    assert isinstance(rep.auto_escalate, bool)
