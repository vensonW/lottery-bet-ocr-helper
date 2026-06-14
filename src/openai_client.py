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

        plain_response = LotteryOcrClient._to_plain_response(response)
        text = LotteryOcrClient._extract_output_text_from_plain(plain_response)
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

        summary = LotteryOcrClient._summarize_response(plain_response)
        raise ValueError(f"无法从 OpenAI 响应中提取文本；响应摘要：{summary}")

    @staticmethod
    def _to_plain_response(response: Any) -> Any:
        """把 OpenAI SDK 对象尽量转成普通 dict，便于兼容不同网关/SDK结构。"""
        if isinstance(response, (dict, list, str, int, float, bool)) or response is None:
            return response
        for method_name in ("model_dump", "to_dict", "dict"):
            method = getattr(response, method_name, None)
            if callable(method):
                try:
                    return method()
                except Exception:
                    pass
        try:
            return json.loads(json.dumps(response, default=lambda obj: getattr(obj, "__dict__", str(obj))))
        except Exception:
            return {"repr": repr(response)}

    @staticmethod
    def _extract_output_text_from_plain(data: Any) -> str:
        """兼容 Responses API、Chat Completions 以及部分中转接口的返回结构。"""
        if isinstance(data, str):
            return data.strip()
        if not isinstance(data, dict):
            return ""

        # Responses API 快捷字段。
        output_text = data.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()

        # Responses API 标准 output/content 结构。
        output = data.get("output")
        if isinstance(output, list):
            chunks: list[str] = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if isinstance(content, str) and content.strip():
                    chunks.append(content)
                    continue
                if not isinstance(content, list):
                    continue
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    text = part.get("text") or part.get("content")
                    if isinstance(text, dict):
                        text = text.get("value") or text.get("text")
                    if isinstance(text, str) and text.strip():
                        chunks.append(text)
                    elif part.get("json") is not None:
                        chunks.append(json.dumps(part["json"], ensure_ascii=False))
                if chunks:
                    return "".join(chunks).strip()

        # Chat Completions 兼容结构：choices[].message.content
        choices = data.get("choices")
        if isinstance(choices, list):
            chunks = []
            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                message = choice.get("message") or {}
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str) and content.strip():
                        chunks.append(content)
                    elif isinstance(content, list):
                        for part in content:
                            if isinstance(part, dict):
                                text = part.get("text") or part.get("content")
                                if isinstance(text, str) and text.strip():
                                    chunks.append(text)
                text = choice.get("text")
                if isinstance(text, str) and text.strip():
                    chunks.append(text)
            if chunks:
                return "".join(chunks).strip()

        return ""

    @staticmethod
    def _summarize_response(data: Any) -> str:
        if not isinstance(data, dict):
            return repr(data)[:800]

        summary: dict[str, Any] = {
            "status": data.get("status"),
            "model": data.get("model"),
            "top_keys": list(data.keys())[:20],
        }
        if data.get("error"):
            summary["error"] = data.get("error")
        if data.get("incomplete_details"):
            summary["incomplete_details"] = data.get("incomplete_details")

        output = data.get("output")
        if isinstance(output, list):
            output_summary = []
            for item in output[:5]:
                if isinstance(item, dict):
                    content = item.get("content")
                    content_types = []
                    if isinstance(content, list):
                        content_types = [part.get("type") for part in content[:5] if isinstance(part, dict)]
                    output_summary.append(
                        {
                            "type": item.get("type"),
                            "status": item.get("status"),
                            "content_types": content_types,
                        }
                    )
            summary["output"] = output_summary

        return json.dumps(summary, ensure_ascii=False, default=str)[:1200]
