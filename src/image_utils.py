from __future__ import annotations

import base64
import mimetypes
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps

from models import CropHint, PreparedImage


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


def list_image_files(folder: Path) -> list[Path]:
    if not folder.exists() or not folder.is_dir():
        raise FileNotFoundError(f"图片文件夹不存在：{folder}")
    return sorted(
        [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS],
        key=lambda p: p.name.lower(),
    )


def _mime_for_format(fmt: str | None, path: Path) -> str:
    if fmt:
        fmt = fmt.upper()
        if fmt == "JPEG":
            return "image/jpeg"
        if fmt == "PNG":
            return "image/png"
        if fmt == "WEBP":
            return "image/webp"
    return mimetypes.guess_type(str(path))[0] or "image/jpeg"


def prepare_image_for_ai(image_path: Path, max_side: int = 2048, jpeg_quality: int = 90) -> PreparedImage:
    with Image.open(image_path) as img:
        img = ImageOps.exif_transpose(img)
        original_width, original_height = img.size
        sent = img
        if max(original_width, original_height) > max_side > 0:
            sent = img.copy()
            sent.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)

        sent_width, sent_height = sent.size
        fmt = (img.format or image_path.suffix.replace(".", "")).upper()
        if fmt not in {"JPEG", "PNG", "WEBP"}:
            fmt = "JPEG"

        buffer = BytesIO()
        save_kwargs = {}
        if fmt == "JPEG":
            if sent.mode not in {"RGB", "L"}:
                sent = sent.convert("RGB")
            save_kwargs = {"quality": jpeg_quality, "optimize": True}
        elif fmt == "PNG":
            save_kwargs = {"optimize": True}
        sent.save(buffer, format=fmt, **save_kwargs)

    mime = _mime_for_format(fmt, image_path)
    data = base64.b64encode(buffer.getvalue()).decode("ascii")
    return PreparedImage(
        path=image_path,
        data_url=f"data:{mime};base64,{data}",
        mime_type=mime,
        original_width=original_width,
        original_height=original_height,
        sent_width=sent_width,
        sent_height=sent_height,
    )


def clamp_crop_to_original(hint: CropHint | None, prepared: PreparedImage, padding_ratio: float = 0.35) -> tuple[int, int, int, int] | None:
    if hint is None or not hint.is_usable():
        return None

    x = int(round(hint.x * prepared.scale_x))
    y = int(round(hint.y * prepared.scale_y))
    w = int(round(hint.w * prepared.scale_x))
    h = int(round(hint.h * prepared.scale_y))
    # AI 给出的局部框有时偏紧：横向多留，避免金额或玩法字被裁掉；
    # 纵向少留且设置上限，避免把上下相邻投注行也截进来。
    pad_x = max(60, int(w * padding_ratio))
    pad_y = max(18, min(42, int(h * 0.28)))
    max_total_height = max(80, min(180, int(h * 1.65)))
    if h + pad_y * 2 > max_total_height:
        pad_y = max(8, (max_total_height - h) // 2)
    left = max(0, x - pad_x)
    top = max(0, y - pad_y)
    right = min(prepared.original_width, x + w + pad_x)
    bottom = min(prepared.original_height, y + h + pad_y)

    if right - left <= 5 or bottom - top <= 5:
        return None
    return left, top, right, bottom


def save_review_crop(
    image_path: Path,
    prepared: PreparedImage,
    hint: CropHint | None,
    output_path: Path,
    max_width: int = 760,
    max_height: int = 360,
    upscale_factor: float = 1.0,
) -> tuple[Path, bool]:
    """保存核查截图。返回：(截图路径, 是否使用整图兜底)。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(image_path) as img:
        img = ImageOps.exif_transpose(img)
        crop_box = clamp_crop_to_original(hint, prepared)
        used_full_image = crop_box is None
        if crop_box is not None:
            img = img.crop(crop_box)
        if upscale_factor and upscale_factor > 1:
            width, height = img.size
            img = img.resize(
                (
                    max(1, int(round(width * upscale_factor))),
                    max(1, int(round(height * upscale_factor))),
                ),
                Image.Resampling.LANCZOS,
            )
        img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
        if img.mode not in {"RGB", "L"}:
            img = img.convert("RGB")
        img.save(output_path, format="PNG", optimize=True)
    return output_path, used_full_image
