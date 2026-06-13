from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PreparedImage:
    path: Path
    data_url: str
    mime_type: str
    original_width: int
    original_height: int
    sent_width: int
    sent_height: int

    @property
    def scale_x(self) -> float:
        return self.original_width / max(1, self.sent_width)

    @property
    def scale_y(self) -> float:
        return self.original_height / max(1, self.sent_height)


@dataclass
class CropHint:
    x: int
    y: int
    w: int
    h: int

    @classmethod
    def from_value(cls, value: Any) -> "CropHint | None":
        if not isinstance(value, dict):
            return None
        try:
            return cls(
                x=int(round(float(value.get("x", 0)))),
                y=int(round(float(value.get("y", 0)))),
                w=int(round(float(value.get("w", 0)))),
                h=int(round(float(value.get("h", 0)))),
            )
        except (TypeError, ValueError):
            return None

    def is_usable(self) -> bool:
        return self.w > 5 and self.h > 5


@dataclass
class OcrItem:
    image_index: int
    item_index: int
    image_file: str
    raw_text: str = ""
    play_type: str = "未知"
    standardized: str = ""
    amount: int = 0
    needs_review: bool = True
    review_reason: str = ""
    crop_hint: CropHint | None = None
    crop_path: Path | None = None
    crop_note: str = ""


@dataclass
class ImageTaskResult:
    image_index: int
    image_path: Path
    image_file: str
    success: bool
    items: list[OcrItem] = field(default_factory=list)
    error_message: str = ""
    prepared: PreparedImage | None = None
    raw_response: dict[str, Any] | None = None


@dataclass
class BatchSummary:
    image_count: int
    success_image_count: int
    failed_image_count: int
    item_count: int
    review_count: int
    total_amount: int
    review_amount: int
