from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from image_utils import prepare_image_for_ai
from models import PreparedImage


class MockLotteryOcrClient:
    """离线演示用客户端，不调用 OpenAI。"""

    def __init__(self, max_image_side: int = 2048, debug_callback: Callable[[str], None] | None = None) -> None:
        self.max_image_side = max_image_side
        self.debug_callback = debug_callback

    def _debug(self, message: str) -> None:
        if self.debug_callback:
            self.debug_callback(message)

    def analyze_image(self, image_path: Path) -> tuple[dict[str, Any], PreparedImage]:
        prepared = prepare_image_for_ai(image_path, max_side=self.max_image_side)
        self._debug(
            "\n".join(
                [
                    f"离线演示：准备处理 {image_path.name}",
                    f"- 原图尺寸：{prepared.original_width}x{prepared.original_height}",
                    f"- 发送尺寸：{prepared.sent_width}x{prepared.sent_height}",
                    "- 未调用 OpenAI",
                ]
            )
        )
        review_crop = {
            "x": int(prepared.sent_width * 0.20),
            "y": int(prepared.sent_height * 0.42),
            "w": int(prepared.sent_width * 0.55),
            "h": int(prepared.sent_height * 0.16),
        }
        data = {
            "image_file": image_path.name,
            "items": [
                {
                    "raw_text": "2X6 — 200",
                    "play_type": "定位",
                    "standardized": "福2*6定各200元",
                    "amount": 200,
                    "needs_review": False,
                    "review_reason": "",
                    "digit_confidence_notes": "",
                    "min_digit_confidence": 100,
                    "crop_hint": None,
                },
                {
                    "raw_text": "疑似511 — 200",
                    "play_type": "未知",
                    "standardized": "",
                    "amount": 200,
                    "needs_review": True,
                    "review_reason": "离线演示：数字不清晰，需人工核查",
                    "digit_confidence_notes": "末位数字：1约65%，7约35%",
                    "min_digit_confidence": 65,
                    "crop_hint": review_crop,
                },
            ],
            "image_level_notes": "离线演示数据",
        }
        self._debug(f"离线演示返回：{data}")
        return data, prepared
