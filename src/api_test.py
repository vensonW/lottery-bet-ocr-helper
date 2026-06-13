from __future__ import annotations


def test_openai_api(
    api_key: str,
    model: str,
    timeout_seconds: float = 60.0,
    base_url: str = "",
    proxy: str = "",
) -> dict[str, str]:
    if not api_key:
        raise ValueError("缺少 OpenAI API Key")
    try:
        from openai import OpenAI
        import httpx
    except ImportError as exc:
        raise RuntimeError("缺少 openai 依赖，请先执行：install.bat") from exc

    client_kwargs = {"api_key": api_key, "timeout": timeout_seconds}
    if base_url:
        client_kwargs["base_url"] = base_url
    if proxy:
        client_kwargs["http_client"] = httpx.Client(proxy=proxy, timeout=timeout_seconds)

    client = OpenAI(**client_kwargs)
    response = client.responses.create(
        model=model,
        input="请只用一句中文回复：接口连通正常。",
        max_output_tokens=80,
        store=False,
    )
    actual_model = getattr(response, "model", "") or ""
    text = getattr(response, "output_text", None)
    if not text:
        output = getattr(response, "output", None)
        chunks: list[str] = []
        if output:
            for item in output:
                content = getattr(item, "content", None)
                if not content:
                    continue
                for part in content:
                    value = getattr(part, "text", None)
                    if value:
                        chunks.append(value)
        text = "".join(chunks).strip() if chunks else str(response)

    return {
        "requested_model": model,
        "response_model": str(actual_model),
        "text": text.strip(),
    }
