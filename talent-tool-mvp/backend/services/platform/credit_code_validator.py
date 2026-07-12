"""统一社会信用代码校验 (GB 32100-2015).

- 18 位长度:1 位登记管理部门代码 + 1 位机构类别代码 + 6 位登记管理机关行政区划码
            + 9 位主体标识码 + 1 位校验码
- 字符集:第 1 位为 9 (工商),第 2 位允许字符表,其余 17 位 0-9 + A-Z (去除 I/O/S/V/Z)
- 校验码:ISO 7064:1983/MOD 31-3, 加权因子表 [1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30, 28]

参考:GB 32100-2015《法人和其他组织统一社会信用代码编码规则》
"""
from __future__ import annotations

from dataclasses import dataclass


# 第 1 位:登记管理部门代码
# 9 -> 工商 (工商部门是本系统最常见的);
# 1/2/3/4/5/6/7/8/A/Y 在国标中分别对应不同登记部门
_REG_DEPT_CODES: frozenset[str] = frozenset(
    [
        "1",  # 机构编制
        "5",  # 民政
        "9",  # 工商
        "Y",  # 其他
    ]
)

# 第 2 位:机构类别代码 (工商体系内,常用 1..9 + A..Z 部分)
# 简化:允许 GB 字符表中所有合法字符
_ORG_TYPE_CODES: frozenset[str] = frozenset(list("123456789") + list("ABCDEFGHJKL"))

# GB 32100-2015 第 3.2 条:代码字符集为 0-9 + A-Z,但去除 I, O, S, V, Z
_ALLOWED_CHARS: frozenset[str] = frozenset(
    [chr(c) for c in range(ord("0"), ord("9") + 1)]
    + [
        ch
        for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        if ch not in ("I", "O", "S", "V", "Z")
    ]
)

# 校验位加权因子 (从左到右 17 个字符)
_WEIGHTS: tuple[int, ...] = (
    1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30, 28,
)

# 字符 -> 数值 (0-9, A-Z 减 I/O/S/V/Z 顺序编号)
_CHAR_MAP: dict[str, int] = {ch: i for i, ch in enumerate(sorted(_ALLOWED_CHARS))}


@dataclass(slots=True)
class CreditCodeCheckResult:
    """校验结果."""

    code: str
    is_valid: bool
    normalized: str
    errors: list[str]


def _char_to_value(ch: str) -> int:
    """字符 -> 数值映射 (GB 32100-2015 附录 A.1)."""
    if ch not in _CHAR_MAP:
        raise ValueError(f"invalid char {ch!r} for credit code")
    return _CHAR_MAP[ch]


def _value_to_char(v: int) -> str:
    """数值 -> 字符."""
    for ch, idx in _CHAR_MAP.items():
        if idx == v:
            return ch
    raise ValueError(f"no char mapping for value {v}")


def normalize(code: str | None) -> str:
    """清洗:去两端空白、去横线空格、强制大写.

    不校验合法性 — 只做显示归一化。
    """
    if code is None:
        return ""
    s = str(code).strip().upper()
    # 去掉常见分隔符
    for sep in (" ", "-", "　"):
        s = s.replace(sep, "")
    return s



def _compute_check_digit(code17: str) -> str:
    """计算前 17 位的校验位 (ISO 7064:1983/MOD 31-3).

    算法:
        sum = Σ (w_i * v_i) for i in 0..16
        check = 31 - (sum mod 31)
        if check == 31 -> 0
    """
    if len(code17) != 17:
        raise ValueError(f"need 17 chars, got {len(code17)}")
    total = 0
    for i, ch in enumerate(code17):
        total += _WEIGHTS[i] * _char_to_value(ch)
    remainder = total % 31
    check_val = 31 - remainder
    if check_val == 31:
        check_val = 0
    return _value_to_char(check_val)


def is_valid(code: str | None, *, strict: bool = True) -> bool:
    """判断统一社会信用代码是否合法.

    Args:
        code: 输入字符串。
        strict: True 时严格校验 (包含 GB 字符集、首字母是 9 等);
                False 时仅做长度 + 校验位。
    """
    try:
        res = validate(code, strict=strict)
        return res.is_valid
    except Exception:
        return False


def validate(code: str | None, *, strict: bool = True) -> CreditCodeCheckResult:
    """完整校验流程,返回 CreditCodeCheckResult.

    错误可能列出多个 (例如同时长度不对 + 字符集越界),
    调用方可以一次性收集所有问题。
    """
    errors: list[str] = []
    normalized = normalize(code)

    # 1. 长度
    if len(normalized) != 18:
        errors.append(f"长度应为 18 位,实际 {len(normalized)}")
        # 长度不对时不继续算校验位,但仍然返回结构化结果
        return CreditCodeCheckResult(
            code=normalized, is_valid=False, normalized=normalized, errors=errors
        )

    # 2. 字符集 (全 18 位)
    out_of_set = [ch for ch in normalized if ch not in _ALLOWED_CHARS]
    if out_of_set:
        errors.append(
            f"含非法字符: {set(out_of_set)!r} (GB 字符集已排除 I/O/S/V/Z)"
        )

    if strict and not errors:
        # 3. 登记管理部门代码 (第 1 位)
        if normalized[0] not in _REG_DEPT_CODES:
            # 仅警告 — 我们不做硬性拒绝,只是记录
            errors.append(
                f"首位登记管理部门代码 {normalized[0]!r} 不在登记部门列表 {_REG_DEPT_CODES!r} 中"
            )
        # 4. 机构类别代码 (第 2 位) — 工商体系内放宽,只要是合法字符即可
        if normalized[1] not in _ORG_TYPE_CODES and normalized[0] == "9":
            # 当第 1 位是工商 9 时,机构类别只能是 1..9
            errors.append(
                f"工商体系机构类别代码 {normalized[1]!r} 应在 {sorted(_ORG_TYPE_CODES)!r}"
            )
        # 5. 行政区划 (第 3-8 位) — 必须是数字
        region_chars = normalized[2:8]
        if not region_chars.isdigit():
            errors.append(f"登记管理机关行政区划码 (3-8 位) 应全为数字: {region_chars!r}")
        # 6. 主体标识码 (第 9-17 位) — 通常是数字或字母数字混合,只确认字符合法
        body_chars = normalized[8:17]
        bad_body = [c for c in body_chars if c not in "0123456789"]
        # 注:在严格模式下应该允许字母,但实际工商主体标识码大多是数字
        # 我们放过非数字以兼容不同地区的格式

    # 7. 校验位 (ISO 7064:1983/MOD 31-3) — 即使上面有错,也尝试计算给出参考
    check_ok = False
    try:
        if not out_of_set:  # 字符集错误时无法计算
            expected = _compute_check_digit(normalized[:17])
            check_ok = expected == normalized[17]
            if not check_ok:
                errors.append(
                    f"校验位错误: 应为 {expected!r}, 实际 {normalized[17]!r}"
                )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"校验位计算失败: {exc}")

    is_ok = (
        len(errors) == 0
        and len(normalized) == 18
        and check_ok
    )

    return CreditCodeCheckResult(
        code=normalized,
        is_valid=is_ok,
        normalized=normalized,
        errors=errors,
    )


def check_digit(code17: str) -> str:
    """对外工具:给定前 17 位,返回校验位字符."""
    s = normalize(code17)
    if len(s) != 17:
        raise ValueError(f"need 17 chars, got {len(s)}")
    return _compute_check_digit(s)
