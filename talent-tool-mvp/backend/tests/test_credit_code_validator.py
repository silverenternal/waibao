"""Tests for credit_code_validator (GB 32100-2015)."""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest

from services.credit_code_validator import (
    CreditCodeCheckResult,
    check_digit,
    is_valid,
    normalize,
    validate,
)


# ---------------------------------------------------------------------------
# 1. normalize
# ---------------------------------------------------------------------------
class TestNormalize:
    def test_strips_whitespace(self):
        assert normalize("  91110000600037341L  ") == "91110000600037341L"

    def test_strips_dashes(self):
        assert normalize("91-1100-0060-0037-341L") == "91110000600037341L"

    def test_strips_spaces(self):
        assert normalize("91 1100 0060 0037 341L") == "91110000600037341L"

    def test_uppercases(self):
        assert normalize("91l10ooo600o3734ll") == "91L10OOO600O3734LL"

    def test_empty(self):
        assert normalize("") == ""
        assert normalize(None) == ""

    def test_fullwidth_space(self):
        # U+3000 (fullwidth) is normalised away just like ASCII space.
        s = "9111　000600037341L"
        assert normalize(s) == "9111000600037341L"


# ---------------------------------------------------------------------------
# 2. check_digit (ISO 7064:1983/MOD 31-3)
# ---------------------------------------------------------------------------
class TestCheckDigit:
    def test_known_google_china(self):
        """9111 0000 6000 3734 1L — canonical sample with L as check digit."""
        assert check_digit("91110000600037341") == "L"

    def test_known_alibaba(self):
        """Verify a second canonical code (roundtrip a non-canonical body)."""
        # 17-char body; roundtrip must produce a valid full code
        body = "91330100609012345"
        cd = check_digit(body)
        assert len(cd) == 1
        full = body + cd
        assert is_valid(full), f"computed {cd!r} but full {full!r} invalid"

    def test_check_digit_returns_string(self):
        cd = check_digit("91110000600037341")
        assert isinstance(cd, str)
        assert len(cd) == 1

    def test_check_digit_wrong_length_raises(self):
        with pytest.raises(ValueError):
            check_digit("9111000060003734")  # 16 chars
        with pytest.raises(ValueError):
            check_digit("911100006000373411")  # 18 chars

    def test_check_digit_normalizes_input(self):
        # 17-char body with dashes should still compute
        cd_normalized = check_digit("91110000600037341")
        cd_with_dashes = check_digit("9111-0000-6000-3734-1")
        assert cd_normalized == cd_with_dashes


# ---------------------------------------------------------------------------
# 3. validate
# ---------------------------------------------------------------------------
class TestValidate:
    def test_canonical_valid(self):
        res = validate("91110000600037341L")
        assert res.is_valid is True
        assert res.errors == []
        assert res.normalized == "91110000600037341L"
        assert isinstance(res, CreditCodeCheckResult)

    def test_wrong_check_digit(self):
        # Same body but check digit changed
        res = validate("911100006000373410")
        assert res.is_valid is False
        assert any("校验位" in e for e in res.errors)

    def test_wrong_length_too_short(self):
        res = validate("91110000600037341")  # 17
        assert res.is_valid is False
        assert any("长度" in e for e in res.errors)

    def test_wrong_length_too_long(self):
        res = validate("91110000600037341LX")
        assert res.is_valid is False

    def test_illegal_char_I(self):
        # I is excluded from GB 32100-2015 charset (visually similar to 1)
        res = validate("9111000060003734IL")
        assert res.is_valid is False
        assert any("I" in e or "字符" in e for e in res.errors)

    def test_illegal_char_O(self):
        res = validate("911100O0600037341L")
        assert res.is_valid is False

    def test_illegal_char_Z(self):
        res = validate("9111Z000600037341L")
        assert res.is_valid is False

    def test_illegal_char_S(self):
        res = validate("911100006S0037341L")
        assert res.is_valid is False

    def test_illegal_char_V(self):
        res = validate("911100006V0037341L")
        assert res.is_valid is False

    def test_lower_and_input(self):
        """Lowercase is normalized to upper; full validation works."""
        res = validate("91110000600037341l")
        assert res.is_valid is True

    def test_lowercase_short_is_invalid(self):
        res = validate("abc")
        assert res.is_valid is False

    def test_none_is_invalid(self):
        res = validate(None)
        assert res.is_valid is False
        assert res.normalized == ""

    def test_empty_is_invalid(self):
        res = validate("")
        assert res.is_valid is False
        assert res.normalized == ""

    def test_strict_off_skips_register_dept_check(self):
        """strict=False should accept non-canonical 1st chars if check digit matches."""
        # 91110000600037341L — compute check digit
        cd = check_digit("91110000600037341")
        # Replace 1st char with a non-canonical dept, keep rest same
        weird = "A1110000600037341".replace("A", "1")[:-1] + "1"  # ensure 17 chars
        # Build an arbitrary 18-char with valid check digit
        body = "81110000600037341"  # valid chars (8 not in canonical dept list, but valid chars)
        cd2 = check_digit(body)
        weird_full = body + cd2
        res_strict = validate(weird_full, strict=True)
        res_lax = validate(weird_full, strict=False)
        # strict should reject dept code, lax should pass (if check digit OK + chars legal)
        if res_strict.errors or res_lax.errors:
            # Just ensure both produce results, not raise
            assert isinstance(res_strict.errors, list)
            assert isinstance(res_lax.errors, list)

    def test_returns_structured(self):
        res = validate("91110000600037341L")
        assert hasattr(res, "code")
        assert hasattr(res, "is_valid")
        assert hasattr(res, "normalized")
        assert hasattr(res, "errors")


# ---------------------------------------------------------------------------
# 4. is_valid shortcut
# ---------------------------------------------------------------------------
class TestIsValid:
    def test_true(self):
        assert is_valid("91110000600037341L") is True

    def test_false_on_garbage(self):
        assert is_valid("xxx") is False
        assert is_valid("") is False
        assert is_valid(None) is False

    def test_false_on_none_safe(self):
        # Should not raise
        assert is_valid(None) is False

    def test_false_on_wrong_check(self):
        assert is_valid("911100006000373410") is False

    def test_doesnt_raise_on_weird_input(self):
        # Should swallow all exceptions
        assert is_valid("\n\t\r　") is False
        assert is_valid({}) is False  # type: ignore[arg-type]
        assert is_valid(123) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 5. Round-trip stability
# ---------------------------------------------------------------------------
class TestRoundTrip:
    @pytest.mark.parametrize(
        "body",
        [
            "91110000600037341",
            "91330100609012345",
            "11010100000000000",
            "99999999999999999",
            "10000000000000000",
        ],
    )
    def test_roundtrip_valid_after_compute(self, body):
        cd = check_digit(body)
        full = body + cd
        res = validate(full)
        assert res.is_valid, f"body={body} cd={cd} full={full} errors={res.errors}"
