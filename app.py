from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def run_cli(argv: list[str] | None = None) -> int:
    from config import load_config, resolve_app_path, save_config

    parser = argparse.ArgumentParser(description="批量投注图片识别并生成Excel")
    parser.add_argument("--cli", action="store_true", help="使用命令行模式")
    parser.add_argument("--input", "-i", required=False, help="图片文件夹路径")
    parser.add_argument("--output", "-o", default=None, help="Excel输出目录；不填则输出到 outputs\\图片文件夹名\\识别结果")
    parser.add_argument("--job", "-j", type=int, default=None, help="并发job数量")
    parser.add_argument("--api-key", default=None, help="OpenAI API Key；为空则读取 config.ini 或环境变量 OPENAI_API_KEY")
    parser.add_argument("--model", default=None, help="OpenAI视觉模型")
    parser.add_argument("--max-side", type=int, default=None, help="发给AI前的最长边像素，默认2048")
    parser.add_argument("--retries", type=int, default=None, help="单图失败重试次数，默认2")
    parser.add_argument("--timeout", type=int, default=None, help="单次 AI 请求超时时间，单位秒，默认读取 config.ini")
    parser.add_argument("--save-config", action="store_true", help="保存本次 API Key、模型、job 等配置到 config.ini")
    parser.add_argument("--mock", action="store_true", help="离线演示模式，不调用OpenAI")
    parser.add_argument("--verbose", action="store_true", help="打印详细日志：AI调用参数摘要、重试、原始返回JSON")
    parser.add_argument("--reprocess-review", action="store_true", help="只重新识别Excel中已标记需人工核查的图片，并替换这些图片的旧记录")
    parser.add_argument("--test-api", action="store_true", help="只测试 OpenAI 接口是否连通，不处理图片")
    args = parser.parse_args(argv)

    config = load_config(ROOT_DIR)
    if args.api_key is not None:
        config.api_key = args.api_key
    if args.model is not None:
        config.model = args.model
    if args.job is not None:
        config.default_job_count = args.job
    if args.output is not None:
        config.default_output_dir = args.output
    if args.max_side is not None:
        config.max_image_side = args.max_side
    if args.retries is not None:
        config.retry_count = args.retries
    if args.timeout is not None:
        config.ai_timeout_seconds = args.timeout

    if args.save_config:
        save_config(ROOT_DIR, config)

    api_key = config.resolved_api_key() if not args.mock else "mock"
    if not api_key and not args.mock:
        raise SystemExit("缺少 OpenAI API Key：请在 config.ini 的 [openai] api_key 中配置，或使用 --api-key。")

    if args.test_api:
        if args.mock:
            print(f"离线测试成功：参数解析正常，当前配置模型：{config.model}")
            return 0
        from api_test import test_openai_api

        print(f"开始测试 OpenAI 接口，模型：{config.model}")
        if config.base_url:
            print(f"使用 base_url：{config.base_url}")
        if config.proxy:
            print(f"使用代理：{config.proxy}")
        try:
            result = test_openai_api(
                api_key,
                config.model,
                timeout_seconds=int(config.ai_timeout_seconds or 60),
                base_url=config.base_url,
                proxy=config.proxy,
            )
        except Exception as exc:
            print("接口测试失败：无法连接到 OpenAI。")
            print(f"错误类型：{type(exc).__name__}")
            print(f"错误信息：{exc}")
            print("建议检查：1) 网络是否能访问 api.openai.com；2) 是否需要代理；3) config.ini 中 base_url/proxy 是否正确；4) API Key 是否正确。")
            return 1
        print("接口测试成功")
        print(f"程序请求模型：{result.get('requested_model', '')}")
        print(f"API响应模型：{result.get('response_model', '') or '响应中未返回model字段'}")
        print(f"AI回复：{result.get('text', '')}")
        return 0

    if not args.input:
        raise SystemExit("缺少图片文件夹：请使用 --input 指定，或仅使用 --test-api 测试接口。")

    from batch_runner import BatchOptions, run_batch
    input_dir = Path(args.input)
    output_dir = (
        resolve_app_path(ROOT_DIR, args.output, "outputs")
        if args.output is not None
        else ROOT_DIR / "outputs" / input_dir.name / "识别结果"
    )

    options = BatchOptions(
        input_dir=input_dir,
        output_dir=output_dir,
        job_count=max(1, int(config.default_job_count or 1)),
        api_key=api_key,
        model=config.model,
        skill_path=ROOT_DIR / "skills" / "lottery_ocr" / "SKILL.md",
        output_name=f"投注识别统计_{input_dir.name}",
        base_url=config.base_url,
        proxy=config.proxy,
        max_image_side=int(config.max_image_side or 2048),
        retry_count=int(config.retry_count or 2),
        mock=args.mock,
        verbose=args.verbose,
        ai_timeout_seconds=int(config.ai_timeout_seconds or 120),
        reprocess_review=args.reprocess_review,
    )

    def on_progress(done: int, total: int, message: str) -> None:
        print(f"[{done}/{total}] {message}", flush=True)

    output_file = run_batch(options, progress_callback=on_progress)
    print(f"完成：{output_file}")
    return 0


def run_gui() -> int:
    try:
        from gui import main
    except ImportError as exc:
        print("无法启动桌面界面，可能缺少 PySide6。", file=sys.stderr)
        print("请先执行：install_gui.bat", file=sys.stderr)
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    return main(ROOT_DIR)


if __name__ == "__main__":
    if "--cli" in sys.argv:
        raise SystemExit(run_cli())
    raise SystemExit(run_gui())
