"""Video splitting and safe cleanup, independent of Telegram handlers."""

import logging
import math
import os
import subprocess

from config import DOWNLOAD_DIR, MAX_FILE_SIZE


MB = 1024 * 1024
TARGET_SIZE_MB = 45
MAX_RETRIES = 2
RETRY_DURATION_MULTIPLIER = 0.8
FFPROBE_TIMEOUT = 30
FFMPEG_TIMEOUT = 300

logger = logging.getLogger(__name__)


def format_size(bytes_size: int) -> str:
    """Format bytes as megabytes."""
    return f'{bytes_size / MB:.1f}MB'


def is_safe_path(path: str, base_dir: str | None = None) -> bool:
    """Check containment after resolving symlinks and Windows junctions."""
    try:
        base = os.path.normcase(os.path.realpath(DOWNLOAD_DIR if base_dir is None else base_dir))
        resolved = os.path.normcase(os.path.realpath(path))
        return os.path.commonpath([base, resolved]) == base
    except (OSError, ValueError, TypeError):
        return False


def _cleanup_parts(parts: list[str], base_dir: str | None = None) -> None:
    """Best-effort deletion of owned files; one failure must not stop cleanup."""
    for part_path in parts:
        if not is_safe_path(part_path, base_dir):
            logger.warning('Unsafe cleanup path: %s', part_path)
            continue
        try:
            if os.path.exists(part_path):
                os.remove(part_path)
        except OSError as error:
            logger.warning('Could not remove %s: %s', part_path, error)


def _get_video_duration(video_path: str) -> float | None:
    """Get a finite, positive duration from ffprobe within a bounded time."""
    try:
        result = subprocess.run(
            [
                'ffprobe', '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                video_path,
            ],
            capture_output=True,
            text=True,
            timeout=FFPROBE_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        logger.error('ffprobe failed: %s', error)
        return None

    if result.returncode != 0:
        logger.error('ffprobe failed: %s', result.stderr)
        return None
    try:
        duration = float(result.stdout.strip())
    except ValueError:
        logger.error('Invalid video duration: %s', result.stdout)
        return None
    if not math.isfinite(duration) or duration <= 0:
        logger.error('Invalid video duration: %s', result.stdout)
        return None
    return duration


def _calculate_parts(file_size: int, duration: float) -> tuple[int, float]:
    """Estimate a part duration using a margin below Telegram's size limit."""
    target_size = MAX_FILE_SIZE * (TARGET_SIZE_MB / 50.0)
    num_parts = int(file_size / target_size) + 1
    return num_parts, duration / num_parts


def _create_video_part(
    video_path: str,
    output_path: str,
    start_time: float,
    part_duration: float,
) -> bool:
    """Copy one interval with ffmpeg, removing incomplete output on failure."""
    try:
        subprocess.run(
            [
                'ffmpeg', '-i', video_path,
                '-ss', str(start_time), '-t', str(part_duration),
                '-c', 'copy', '-y', output_path,
            ],
            capture_output=True,
            check=True,
            timeout=FFMPEG_TIMEOUT,
        )
        return True
    except (OSError, subprocess.SubprocessError) as error:
        logger.error('ffmpeg failed: %s', error)
        _cleanup_parts([output_path])
        return False


def _split_part_with_retry(
    video_path: str,
    output_path: str,
    start_time: float,
    initial_duration: float,
    part_index: int,
    total_parts: int,
) -> tuple[str, float] | None:
    """Return a part and its accepted duration, shortening oversized attempts."""
    part_duration = initial_duration
    accepted = False
    try:
        for attempt in range(MAX_RETRIES):
            if not _create_video_part(video_path, output_path, start_time, part_duration):
                return None
            actual_size = os.path.getsize(output_path)
            if actual_size == 0:
                logger.error('ffmpeg produced an empty part: %s', output_path)
                return None
            if actual_size <= MAX_FILE_SIZE:
                logger.info(
                    'Part %s (initial estimate: %s): %s',
                    part_index, total_parts, format_size(actual_size),
                )
                accepted = True
                return output_path, part_duration

            logger.warning('Part %s exceeds size limit: %s', part_index, format_size(actual_size))
            _cleanup_parts([output_path])
            if attempt < MAX_RETRIES - 1:
                part_duration *= RETRY_DURATION_MULTIPLIER
        return None
    finally:
        if not accepted:
            _cleanup_parts([output_path])


def split_video(video_path: str) -> list[str]:
    """Split the entire video into files within Telegram's size limit."""
    if not is_safe_path(video_path):
        logger.error('Unsafe video path: %s', video_path)
        return []

    attempted_outputs: list[str] = []
    output_files: list[str] = []
    completed = False
    try:
        duration = _get_video_duration(video_path)
        if duration is None:
            return []
        num_parts, part_duration = _calculate_parts(os.path.getsize(video_path), duration)
        stem, _ = os.path.splitext(video_path)
        cursor = 0.0

        while cursor < duration:
            part_index = len(output_files) + 1
            output_path = f'{stem}_part{part_index}.mp4'
            if not is_safe_path(output_path):
                logger.error('Unsafe output path: %s', output_path)
                return []
            attempted_outputs.append(output_path)

            remaining = duration - cursor
            # Repeated fractional durations can leave a rounding-sized tail.
            # Include it in the final interval rather than creating an empty part.
            current_duration = (
                remaining
                if math.isclose(remaining, part_duration, rel_tol=1e-12, abs_tol=1e-9)
                else min(part_duration, remaining)
            )
            result = _split_part_with_retry(
                video_path, output_path, cursor,
                current_duration, part_index, num_parts,
            )
            if result is None:
                return []

            part_path, accepted_duration = result
            output_files.append(part_path)
            # A retry may shorten a part. Advance by what was actually accepted
            # so the next part begins exactly where this one ends.
            cursor = min(duration, cursor + accepted_duration)

        completed = True
        return output_files
    except Exception as error:
        logger.error('Video splitting failed: %s', error)
        return []
    finally:
        if not completed:
            _cleanup_parts(attempted_outputs)
