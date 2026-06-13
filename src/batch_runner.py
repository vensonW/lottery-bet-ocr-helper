from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from dataclasses import dataclass
from threading import Lock
from pathlib import Path
from typing import Callable

from excel_writer import (
    ensure_workbook_writable,
    read_existing_image_files,
    read_review_image_files,
    upgrade_existing_workbook_layout,
    write_workbook,
)
from image_utils import list_image_files, prepare_image_for_ai, save_review_crop
from models import ImageTaskResult
from openai_client import LotteryOcrClient
from validator import make_failure_result, validate_ai_result


ProgressCallback = Callable[[int, int, str], None]


@dataclass
class BatchOptions:
    input_dir: Path
    output_dir: Path
    job_count: int
    api_key: str
    model: str
    skill_path: Path
    output_name: str = ""
    base_url: str = ""
    proxy: str = ""
    max_image_side: int = 2048
    retry_count: int = 2
    mock: bool = False
    verbose: bool = False
    ai_timeout_seconds: int = 120
    reprocess_review: bool = False


def run_batch(options: BatchOptions, progress_callback: ProgressCallback | None = None) -> Path:
    image_files = list_image_files(options.input_dir)
    if not image_files:
        raise FileNotFoundError(f"文件夹中没有图片：{options.input_dir}")

    output_stem = options.output_name or f"投注识别统计_{options.input_dir.name}"
    run_output_dir = options.output_dir
    crops_dir = run_output_dir / "_row_crops"
    output_file = run_output_dir / f"{output_stem}.xlsx"
    run_output_dir.mkdir(parents=True, exist_ok=True)
    ensure_workbook_writable(output_file)
    upgrade_existing_workbook_layout(output_file)

    existing_image_files = read_existing_image_files(output_file)
    review_image_files = read_review_image_files(output_file) if options.reprocess_review else set()
    if options.reprocess_review:
        image_files_with_index = [
            (idx, image_path)
            for idx, image_path in enumerate(image_files)
            if image_path.name in review_image_files
        ]
        skipped_count = len(image_files) - len(image_files_with_index)
    elif existing_image_files:
        before_count = len(image_files)
        image_files_with_index = [
            (idx, image_path)
            for idx, image_path in enumerate(image_files)
            if image_path.name not in existing_image_files
        ]
        skipped_count = before_count - len(image_files_with_index)
    else:
        image_files_with_index = list(enumerate(image_files))
        skipped_count = 0

    total = len(image_files_with_index)
    done = 0
    done_lock = Lock()
    results: list[ImageTaskResult] = []
    job_count = max(1, min(int(options.job_count or 1), total or 1))
    buckets: list[list[tuple[int, Path]]] = [[] for _ in range(job_count)]
    for idx, image_path in image_files_with_index:
        buckets[idx % job_count].append((idx, image_path))

    def emit(message: str) -> None:
        if progress_callback:
            with done_lock:
                progress_callback(done, total, message)

    def debug(message: str) -> None:
        if options.verbose:
            emit(f"[详细] {message}")

    def mark_image_done(message: str) -> None:
        nonlocal done
        if progress_callback:
            with done_lock:
                done += 1
                progress_callback(done, total, message)
        else:
            with done_lock:
                done += 1

    def process_bucket(bucket_id: int, bucket: list[tuple[int, Path]]) -> list[ImageTaskResult]:
        local_results: list[ImageTaskResult] = []
        try:
            if options.mock:
                from mock_openai_client import MockLotteryOcrClient

                client = MockLotteryOcrClient(max_image_side=options.max_image_side, debug_callback=debug)
            else:
                client = LotteryOcrClient(
                    api_key=options.api_key,
                    model=options.model,
                    skill_path=options.skill_path,
                    max_image_side=options.max_image_side,
                    timeout_seconds=options.ai_timeout_seconds,
                    base_url=options.base_url,
                    proxy=options.proxy,
                    debug_callback=debug,
                )
        except Exception as exc:
            for image_index, image_path in bucket:
                image_started = time.monotonic()
                try:
                    prepared = prepare_image_for_ai(image_path, max_side=options.max_image_side)
                except Exception:
                    prepared = None
                local_results.append(make_failure_result(image_index, image_path, exc, prepared=prepared))
                elapsed = time.monotonic() - image_started
                mark_image_done(f"job{bucket_id} 失败：{image_path.name}，耗时 {elapsed:.1f} 秒")
            return local_results

        for image_index, image_path in bucket:
            if not options.reprocess_review and image_path.name in read_existing_image_files(output_file):
                mark_image_done(f"job{bucket_id} 跳过：{image_path.name}，Excel已存在记录，未发送AI")
                continue
            image_started = time.monotonic()
            last_error: Exception | None = None
            prepared = None
            for attempt in range(options.retry_count + 1):
                try:
                    debug(f"job{bucket_id} 开始调用 AI：{image_path.name}，第 {attempt + 1} 次")
                    data, prepared = _analyze_image_with_heartbeat(client, image_path, options, debug, bucket_id)
                    result = validate_ai_result(data, image_index, image_path, prepared)
                    debug(
                        f"job{bucket_id} 解析完成：{image_path.name}，"
                        f"返回 {len(result.items)} 行，需核查 {sum(1 for item in result.items if item.needs_review)} 行"
                    )
                    local_results.append(result)
                    elapsed = time.monotonic() - image_started
                    mark_image_done(f"job{bucket_id} 完成：{image_path.name}，耗时 {elapsed:.1f} 秒")
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc
                    debug(f"job{bucket_id} 调用失败：{image_path.name}，第 {attempt + 1} 次，错误：{exc}")
                    if attempt < options.retry_count:
                        time.sleep(min(2.0 * (attempt + 1), 6.0))
            if last_error is not None:
                try:
                    prepared = prepared or prepare_image_for_ai(image_path, max_side=options.max_image_side)
                except Exception:
                    prepared = None
                local_results.append(make_failure_result(image_index, image_path, last_error, prepared=prepared))
                elapsed = time.monotonic() - image_started
                mark_image_done(f"job{bucket_id} 失败：{image_path.name}，耗时 {elapsed:.1f} 秒")
        return local_results

    if options.reprocess_review:
        emit(f"启用 --reprocess-review：Excel中需人工核查图片 {len(review_image_files)} 张，本次可在文件夹中找到 {total} 张")
    elif skipped_count:
        emit(f"发现 {len(image_files)} 张图片，Excel已有记录 {skipped_count} 张，跳过不再发送AI")
    if total == 0:
        if options.reprocess_review:
            emit(f"没有找到需要重新识别的人工核查图片，直接使用已有Excel：{output_file}")
        else:
            emit(f"没有新增图片需要识别，直接使用已有Excel：{output_file}")
        return output_file

    if options.reprocess_review:
        emit(f"发现 {len(image_files)} 张图片，待重新处理 {total} 张，启动 {job_count} 个job")
        emit(f"重新识别结果将替换这些图片的旧记录：{output_file}")
    else:
        emit(f"发现 {len(image_files)} 张图片，待处理 {total} 张，启动 {job_count} 个job")
        emit(f"新增识别结果将追加写入：{output_file}")
    with ThreadPoolExecutor(max_workers=job_count) as executor:
        future_map = {
            executor.submit(process_bucket, bucket_id, bucket): (bucket_id, bucket)
            for bucket_id, bucket in enumerate(buckets, start=1)
            if bucket
        }
        for future in as_completed(future_map):
            bucket_id, bucket = future_map[future]
            try:
                bucket_results = future.result()
            except Exception as exc:
                bucket_results = []
                for image_index, image_path in bucket:
                    image_started = time.monotonic()
                    try:
                        prepared = prepare_image_for_ai(image_path, max_side=options.max_image_side)
                    except Exception:
                        prepared = None
                    bucket_results.append(make_failure_result(image_index, image_path, exc, prepared=prepared))
                    elapsed = time.monotonic() - image_started
                    mark_image_done(f"job{bucket_id} 异常失败：{image_path.name}，耗时 {elapsed:.1f} 秒")
            results.extend(bucket_results)
            emit(f"job{bucket_id} 完成 {len(bucket_results)} 张")

    results.sort(key=lambda r: r.image_index)
    debug("开始生成识别行截图")
    _create_review_crops(results, crops_dir)
    debug("开始写入 Excel")
    replace_image_files = {result.image_file for result in results} if options.reprocess_review else None
    write_workbook(results, output_file, replace_image_files=replace_image_files)
    if progress_callback:
        progress_callback(total, total, f"Excel已更新：{output_file}")
    return output_file


def _create_review_crops(results: list[ImageTaskResult], crops_dir: Path) -> None:
    for result in results:
        if result.prepared is None:
            continue
        for item in result.items:
            crop_name = f"img{result.image_index + 1:04d}_row{item.item_index + 1:03d}.png"
            try:
                crop_path, used_full = save_review_crop(
                    result.image_path,
                    result.prepared,
                    item.crop_hint,
                    crops_dir / crop_name,
                )
                item.crop_path = crop_path
                if item.needs_review and used_full:
                    item.crop_note = "AI无法定位局部区域，已附原图核查"
                    if item.crop_note not in item.review_reason:
                        item.review_reason = f"{item.review_reason}；{item.crop_note}" if item.review_reason else item.crop_note
            except Exception as exc:
                item.crop_note = f"截图生成失败：{exc}"
                if item.needs_review and item.crop_note not in item.review_reason:
                    item.review_reason = f"{item.review_reason}；{item.crop_note}" if item.review_reason else item.crop_note


def _analyze_image_with_heartbeat(client, image_path: Path, options: BatchOptions, debug: Callable[[str], None], bucket_id: int):
    if not options.verbose:
        return client.analyze_image(image_path)

    heartbeat_seconds = 10
    started = time.monotonic()
    debug(f"job{bucket_id} 等待 AI 返回，超时时间 {options.ai_timeout_seconds} 秒：{image_path.name}")
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(client.analyze_image, image_path)
    try:
        while True:
            elapsed = int(time.monotonic() - started)
            remaining = int(options.ai_timeout_seconds - elapsed)
            try:
                return future.result(timeout=heartbeat_seconds)
            except TimeoutError:
                elapsed = int(time.monotonic() - started)
                remaining = int(options.ai_timeout_seconds - elapsed)
                if elapsed >= options.ai_timeout_seconds:
                    future.cancel()
                    raise TimeoutError(f"AI 请求超过 {options.ai_timeout_seconds} 秒仍未返回：{image_path.name}")
                debug(f"job{bucket_id} 仍在等待 AI 返回：{image_path.name}，已等待 {elapsed} 秒，剩余约 {max(0, remaining)} 秒")
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
