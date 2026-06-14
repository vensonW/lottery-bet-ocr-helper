from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from models import CropHint, ImageTaskResult, OcrItem, PreparedImage


POSITION_SYMBOL_RE = re.compile(r"[xX×＊*✕✖╳]")
GROUP_STANDARDIZED_RE = re.compile(r"福(?P<digits>\d{3,})(?P<group_type>组三|组六)")
SAME_DIGIT_STANDARDIZED_RE = re.compile(r"福(?:胆)?(?P<digits>(?P<digit>\d)(?P=digit){2,})(?:组三|组六|直)?各(?P<amount>\d+)元")
DAN_STANDARDIZED_RE = re.compile(r"福胆(?P<digits>\d+)各\d+元")
RAW_NUMBER_OR_POSITION_RE = re.compile(r"[0-9xX×＊*✕✖╳]+")
POSITION_STANDARDIZED_RE = re.compile(r"福(?P<body>[0-9*\-—–－\s]+)定各(?P<amount>\d+)元")


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _as_confidence(value: Any, default: int = 100) -> int:
    confidence = _as_int(value, default)
    return max(0, min(100, confidence))


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "是"}
    return bool(value)


def validate_ai_result(
    data: dict[str, Any],
    image_index: int,
    image_path: Path,
    prepared: PreparedImage,
) -> ImageTaskResult:
    items_data = data.get("items")
    result = ImageTaskResult(
        image_index=image_index,
        image_path=image_path,
        image_file=image_path.name,
        success=True,
        prepared=prepared,
        raw_response=data,
    )

    if not isinstance(items_data, list) or not items_data:
        result.items.append(
            OcrItem(
                image_index=image_index,
                item_index=0,
                image_file=image_path.name,
                raw_text="未识别到投注内容",
                play_type="未知",
                standardized="",
                amount=0,
                needs_review=True,
                review_reason="AI未返回任何投注行，需人工核查整图",
                crop_hint=None,
            )
        )
        return result

    for idx, item_data in enumerate(items_data):
        if not isinstance(item_data, dict):
            result.items.append(
                OcrItem(
                    image_index=image_index,
                    item_index=idx,
                    image_file=image_path.name,
                    raw_text="AI返回的投注行格式异常",
                    play_type="未知",
                    standardized="",
                    amount=0,
                    needs_review=True,
                    review_reason="AI返回的投注行不是对象，需人工核查",
                    crop_hint=None,
                )
            )
            continue

        item = OcrItem(
            image_index=image_index,
            item_index=idx,
            image_file=image_path.name,
            raw_text=str(item_data.get("raw_text") or "").strip(),
            play_type=str(item_data.get("play_type") or "未知").strip() or "未知",
            standardized=str(item_data.get("standardized") or "").strip(),
            amount=_as_int(item_data.get("amount"), 0),
            needs_review=_as_bool(item_data.get("needs_review")),
            review_reason=str(item_data.get("review_reason") or "").strip(),
            crop_hint=CropHint.from_value(item_data.get("crop_hint")),
        )
        _apply_digit_confidence(
            item,
            _as_confidence(item_data.get("min_digit_confidence", 100), 100),
            str(item_data.get("digit_confidence_notes") or "").strip(),
        )
        _apply_safety_checks(item)
        result.items.append(item)

    return result


def make_failure_result(image_index: int, image_path: Path, error: Exception | str, prepared: PreparedImage | None = None) -> ImageTaskResult:
    reason = str(error)
    return ImageTaskResult(
        image_index=image_index,
        image_path=image_path,
        image_file=image_path.name,
        success=False,
        error_message=reason,
        prepared=prepared,
        items=[
            OcrItem(
                image_index=image_index,
                item_index=0,
                image_file=image_path.name,
                raw_text="AI调用失败或图片无法识别",
                play_type="未知",
                standardized="",
                amount=0,
                needs_review=True,
                review_reason=f"处理失败，需人工核查：{reason}",
                crop_hint=None,
            )
        ],
    )


def _mark_review(item: OcrItem, reason: str) -> None:
    item.needs_review = True
    if reason and reason not in item.review_reason:
        item.review_reason = f"{item.review_reason}；{reason}" if item.review_reason else reason


def _has_meaningful_confidence_notes(notes: str) -> bool:
    if not notes.strip():
        return False
    ignored_notes = {"无", "无不确定数字", "全部确定", "全部>=90%", "全部大于等于90%"}
    return notes.strip() not in ignored_notes


def _apply_digit_confidence(item: OcrItem, min_digit_confidence: int, notes: str) -> None:
    """AI认为任一数字低于90%把握时，强制人工核查并把概率估计写入备注。"""
    has_notes = _has_meaningful_confidence_notes(notes)

    if min_digit_confidence < 90:
        if has_notes:
            reason = f"数字识别置信度低于90%，最低置信度{min_digit_confidence}%；概率估计：{notes}"
        else:
            reason = f"数字识别置信度低于90%，最低置信度{min_digit_confidence}%；概率估计：AI未提供"
        _mark_review(item, reason)
        return

    if not has_notes:
        return

    if "%" in notes or "％" in notes:
        reason = f"数字识别置信度低于90%，概率估计：{notes}"
    else:
        reason = f"数字识别置信度低于90%，需人工核查：{notes}"
    _mark_review(item, reason)


def _raw_text_before_amount(item: OcrItem) -> str:
    raw_text = item.raw_text.strip()
    if not raw_text or item.amount <= 0:
        return raw_text

    # 尽量去掉行尾金额，避免把金额当成投注数字串。
    amount = re.escape(str(item.amount))
    match = re.search(rf"^(.*?)(?:[-—–－~～=＝各\s]+){amount}\s*(?:元)?\s*$", raw_text)
    if match and match.group(1).strip():
        return match.group(1).strip()
    return raw_text


def _first_digit_sequence_before_amount(item: OcrItem) -> str:
    text = _raw_text_before_amount(item)
    matches = re.findall(r"\d+", text)
    if not matches:
        return ""
    return matches[0]


def _first_position_sequence_before_amount(item: OcrItem) -> str:
    text = _raw_text_before_amount(item)
    for match in RAW_NUMBER_OR_POSITION_RE.findall(text):
        if re.search(r"\d", match):
            return POSITION_SYMBOL_RE.sub("*", match)
    return ""


def _fill_standardized_candidate(item: OcrItem) -> None:
    """核查项也尽量填写候选标准化结果，方便人工直接对照修改。"""
    if item.standardized or item.amount <= 0:
        return

    if item.play_type == "直选组选混合":
        text = _raw_text_before_amount(item)
        match = re.search(r"(?P<digits>\d+).*?直\s*(?P<direct>\d+).*?组\s*(?P<group>\d+)", text)
        if match:
            item.standardized = (
                f"福{match.group('digits')}直各{match.group('direct')}元"
                f"组各{match.group('group')}元"
            )
        return

    if item.play_type == "定位":
        position_digits = _first_position_sequence_before_amount(item)
        if position_digits:
            item.standardized = f"福{position_digits}定各{item.amount}元"
        return

    digits = _first_digit_sequence_before_amount(item)
    if not digits:
        return

    if item.play_type == "未知":
        # AI 有时会因为“未标注玩法”返回未知并留空标准化。
        # 对能按明确规则推断的内容直接补候选；仍无法确认玩法的两位数，至少展示可核查候选文本。
        position_digits = _first_position_sequence_before_amount(item)
        if POSITION_SYMBOL_RE.search(position_digits):
            item.play_type = "定位"
            item.standardized = f"福{position_digits}定各{item.amount}元"
        elif len(digits) == 1:
            item.play_type = "胆码"
            item.standardized = f"福胆{digits}各{item.amount}元"
        elif len(digits) >= 3:
            if len(set(digits)) == 1:
                item.play_type = "直选"
                item.standardized = f"福{digits}直各{item.amount}元"
            else:
                item.play_type = "组六"
                item.standardized = f"福{digits}组六各{item.amount}元"
        else:
            item.standardized = f"待核查：{digits}各{item.amount}元（玩法未确认）"
        return

    if item.play_type == "胆码":
        item.standardized = f"福胆{digits}各{item.amount}元"
    elif item.play_type in {"组三", "组六"}:
        item.standardized = f"福{digits}{item.play_type}各{item.amount}元"
    elif item.play_type == "直选":
        item.standardized = f"福{digits}直各{item.amount}元"


def _is_non_decreasing_digits(digits: str) -> bool:
    return all(left <= right for left, right in zip(digits, digits[1:]))


def _maybe_fix_ascending_group_digits(digits: str) -> str | None:
    """历史兼容占位：不再自动修正组选数字，避免猜错。"""
    return None


def _looks_like_common_ascending_ocr_risk(digits: str) -> bool:
    """识别常见升序误读风险，如 23479 被读成 23419。"""
    for idx, char in enumerate(digits):
        if char != "1" or idx == 0 or idx == len(digits) - 1:
            continue
        fixed = f"{digits[:idx]}7{digits[idx + 1:]}"
        if _is_non_decreasing_digits(fixed):
            return True
    return False


def _apply_same_digit_direct_priority(item: OcrItem) -> None:
    """连续3个及以上相同数字优先按直选处理，高于默认组选规则。"""
    if item.play_type in {"定位", "直选组选混合"}:
        return

    match = SAME_DIGIT_STANDARDIZED_RE.search(item.standardized)
    if not match:
        return

    digits = match.group("digits")
    item.play_type = "直选"
    item.standardized = f"福{digits}直各{item.amount}元"


def _apply_dan_digit_count_check(item: OcrItem) -> None:
    if item.play_type != "胆码" and "胆" not in item.standardized:
        return

    match = DAN_STANDARDIZED_RE.search(item.standardized)
    if not match:
        return

    digits = match.group("digits")
    if len(digits) > 1:
        _mark_review(item, "胆码后出现多个数字，需确认具体胆码")


def _apply_group_ascending_checks(item: OcrItem) -> None:
    if item.play_type not in {"组三", "组六"}:
        return

    match = GROUP_STANDARDIZED_RE.search(item.standardized)
    if not match:
        return

    digits = match.group("digits")
    if not _is_non_decreasing_digits(digits):
        if _looks_like_common_ascending_ocr_risk(digits):
            _mark_review(item, "组选数字串不符合从小到大书写规律，疑似1/7等数字误识别，需人工核查")
        else:
            _mark_review(item, "组选数字串不符合从小到大书写规律，需核查是否识别错误")


def _normalize_position_standardized(item: OcrItem) -> None:
    if item.play_type != "定位" and "定各" not in item.standardized:
        return

    match = POSITION_STANDARDIZED_RE.search(item.standardized)
    if not match:
        return

    body = match.group("body")
    # 定位数字串中只保留数字和*。数字与X/*之间的空格或误加的-不属于定位内容。
    normalized_body = re.sub(r"[^0-9*]", "", body)
    if normalized_body and normalized_body != body:
        item.standardized = f"福{normalized_body}定各{match.group('amount')}元"


def _apply_safety_checks(item: OcrItem) -> None:
    if item.amount < 0:
        item.amount = 0
        _mark_review(item, "金额为负数，需人工核查")
    if item.amount == 0:
        _mark_review(item, "金额无法确认或为0")
    if item.play_type not in {"胆码", "组三", "组六", "定位", "直选", "直选组选混合", "未知"}:
        item.play_type = "未知"
        _mark_review(item, "玩法类型不在允许范围内")
    if not item.raw_text:
        _mark_review(item, "原图识别内容为空")

    # 即使需要人工核查，也尽量填入候选标准化结果，便于人工在Excel中直接核对。
    _fill_standardized_candidate(item)

    if not item.standardized:
        _mark_review(item, "标准化结果为空")

    _normalize_position_standardized(item)

    # 最高优先级：999、5555 这类连续3个及以上相同数字，按直选，不按默认组六/组三。
    _apply_same_digit_direct_priority(item)

    # 胆码只能跟一个数字；如“胆24”不能盲猜成胆2或胆4，必须人工核查。
    _apply_dan_digit_count_check(item)

    if item.play_type == "未知":
        _mark_review(item, "玩法无法确认")

    # 组选数字通常按从小到大书写。典型场景：23479 被误识别成 23419。
    # 程序不再自动修正数字，只标记人工核查，避免猜错。直选不做该检查。
    _apply_group_ascending_checks(item)

    # 定位防盲猜：标准化中出现*，但原始识别内容没有明确定位符号时，必须人工核查。
    if "*" in item.standardized:
        raw_symbol_count = len(POSITION_SYMBOL_RE.findall(item.raw_text))
        std_symbol_count = item.standardized.count("*")
        if raw_symbol_count < std_symbol_count:
            _mark_review(item, "定位符号数量与原图可见符号不一致，禁止盲目把不确定数字转为*")

    # 如果被标为定位但没有任何可见定位符号，也必须核查。
    if item.play_type == "定位" and not POSITION_SYMBOL_RE.search(item.raw_text):
        _mark_review(item, "原图识别内容中未见明确定位符号，定位结果需核查")

    if item.needs_review and not item.review_reason:
        item.review_reason = "AI标记需人工核查，但未给出具体原因"
    if not item.needs_review:
        # 正常项备注必须为空。
        item.review_reason = ""
