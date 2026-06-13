from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from image_utils import prepare_image_for_ai
from models import PreparedImage
from schema import LOTTERY_OCR_SCHEMA


def test_openai_api(api_key: str, model: str, timeout_seconds: float = 60.0) -> str:
    if not api_key:
        raise ValueError("缺少 OpenAI API Key")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("缺少 openai 依赖，请先执行：install.bat") from exc

    client = OpenAI(api_key=api_key, timeout=timeout_seconds)
    response = client.responses.create(
        model=model,
        input="请只用一句中文回复：接口连通正常，并说明本次请求使用的模型名称。",
        max_output_tokens=120,
        store=False,
    )
    text = getattr(response, "output_text", None)
    if text:
        return text.strip()
    return LotteryOcrClient._extract_output_text(response).strip()


class LotteryOcrClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        skill_path: Path,
        max_image_side: int = 2048,
        timeout_seconds: float = 120.0,
        base_url: str = "",
        proxy: str = "",
        debug_callback: Callable[[str], None] | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("缺少 OpenAI API Key")
        try:
            from openai import OpenAI
            import httpx
        except ImportError as exc:
            raise RuntimeError("缺少 openai 依赖，请先执行：pip install -r requirements.txt") from exc

        client_kwargs = {"api_key": api_key, "timeout": timeout_seconds}
        if base_url:
            client_kwargs["base_url"] = base_url
        if proxy:
            client_kwargs["http_client"] = httpx.Client(proxy=proxy, timeout=timeout_seconds)
        self.client = OpenAI(**client_kwargs)
        self.model = model
        self.skill_path = skill_path
        self.max_image_side = max_image_side
        self.skill_text = skill_path.read_text(encoding="utf-8")
        self.debug_callback = debug_callback

    def _debug(self, message: str) -> None:
        if self.debug_callback:
            self.debug_callback(message)

    def analyze_image(self, image_path: Path) -> tuple[dict[str, Any], PreparedImage]:
        prepared = prepare_image_for_ai(image_path, max_side=self.max_image_side)
        prompt = (
            f"请识别当前图片：{image_path.name}\n"
            f"发送给你的图片像素尺寸为：宽 {prepared.sent_width}，高 {prepared.sent_height}。\n"
            "所有 crop_hint 坐标必须基于这个像素尺寸，左上角为(0,0)，单位为像素。\n"
            "请严格按 SKILL.md 和 JSON Schema 返回结果。不要输出 Markdown 或解释文字。"
        )
        instructions = (
            "你必须严格执行下面的 SKILL.md 规则，并输出符合 JSON Schema 的结构化数据。\n\n"
            "=== SKILL.md 开始 ===\n"
            f"{self.skill_text}\n"
            "=== SKILL.md 结束 ==="
        )
        self._debug(
            "\n".join(
                [
                    f"准备发送给 AI：{image_path.name}",
                    f"- 原图尺寸：{prepared.original_width}x{prepared.original_height}",
                    f"- 发送尺寸：{prepared.sent_width}x{prepared.sent_height}",
                    f"- MIME：{prepared.mime_type}",
                    f"- 模型：{self.model}",
                    f"- prompt：{prompt}",
                    f"- SKILL.md 字数：{len(self.skill_text)}",
                    "- 图片 base64 内容已省略",
                ]
            )
        )

        response = self.client.responses.create(
            model=self.model,
            instructions=instructions,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {
                            "type": "input_image",
                            "image_url": prepared.data_url,
                            "detail": "high",
                        },
                    ],
                }
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "lottery_ocr_response",
                    "description": "投注图片识别结果",
                    "schema": LOTTERY_OCR_SCHEMA,
                    "strict": True,
                },
            },
            max_output_tokens=6000,
            store=False,
        )
        text = self._extract_output_text(response)
        self._debug(f"AI 原始返回：{text}")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"AI返回不是合法JSON：{text[:500]}") from exc
        return data, prepared

    @staticmethod
    def _extract_output_text(response: Any) -> str:
        text = getattr(response, "output_text", None)
        if text:
            return text
        # 兼容 SDK 对象或 dict 的不同结构。
        output = getattr(response, "output", None)
        if output is None and isinstance(response, dict):
            output = response.get("output")
        if output:
            chunks: list[str] = []
            for item in output:
                content = getattr(item, "content", None)
                if content is None and isinstance(item, dict):
                    content = item.get("content")
                if not content:
                    continue
                for part in content:
                    value = getattr(part, "text", None)
                    if value is None and isinstance(part, dict):
                        value = part.get("text")
                    if value:
                        chunks.append(value)
            if chunks:
                return "".join(chunks)
        raise ValueError("无法从 OpenAI 响应中提取文本")
