"""Regression tests for splitting, subprocess failures, and safe cleanup."""

import os
import subprocess
from pathlib import Path

import pytest

import media


MB = 1024 * 1024


@pytest.fixture
def download_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    directory = tmp_path / 'downloads'
    directory.mkdir()
    monkeypatch.setattr(media, 'DOWNLOAD_DIR', str(directory))
    return directory


def write_file(path, size):
    with open(path, 'wb') as output:
        output.truncate(size)


def test_retry_preserves_every_interval_including_tail(download_dir, monkeypatch):
    source = download_dir / 'video.mp4'
    write_file(source, 100 * MB)
    intervals = {}
    attempts = 0

    def run(command, **kwargs):
        nonlocal attempts
        if command[0] == 'ffprobe':
            return subprocess.CompletedProcess(command, 0, '300.0', '')
        attempts += 1
        start = float(command[command.index('-ss') + 1])
        duration = float(command[command.index('-t') + 1])
        write_file(command[-1], (55 if attempts == 1 else 40) * MB)
        intervals[command[-1]] = (start, duration)
        return subprocess.CompletedProcess(command, 0, b'', b'')

    monkeypatch.setattr(media.subprocess, 'run', run)

    parts = media.split_video(str(source))

    assert [intervals[part] for part in parts] == [
        (0, 80), (80, 100), (180, 100), (280, 20),
    ]
    assert all(Path(part).stat().st_size <= 50 * MB for part in parts)


def test_fractional_durations_do_not_create_near_zero_tail(download_dir, monkeypatch):
    source = download_dir / 'video.mp4'
    write_file(source, 270 * MB)
    intervals = []

    def run(command, **kwargs):
        if command[0] == 'ffprobe':
            return subprocess.CompletedProcess(command, 0, '300', '')
        intervals.append((
            float(command[command.index('-ss') + 1]),
            float(command[command.index('-t') + 1]),
        ))
        write_file(command[-1], MB)
        return subprocess.CompletedProcess(command, 0, b'', b'')

    monkeypatch.setattr(media.subprocess, 'run', run)

    parts = media.split_video(str(source))

    assert len(parts) == 7
    assert all(part_duration > 42 for _, part_duration in intervals)
    assert intervals[-1][0] + intervals[-1][1] == 300


def test_empty_output_is_rejected_and_removed(download_dir, monkeypatch):
    source = download_dir / 'video.mp4'
    write_file(source, 10 * MB)

    def run(command, **kwargs):
        if command[0] == 'ffprobe':
            return subprocess.CompletedProcess(command, 0, '10', '')
        write_file(command[-1], 0)
        return subprocess.CompletedProcess(command, 0, b'', b'')

    monkeypatch.setattr(media.subprocess, 'run', run)

    assert media.split_video(str(source)) == []
    assert sorted(download_dir.iterdir()) == [source]


def test_output_name_preserves_directory_and_non_mp4_source(download_dir, monkeypatch):
    directory = download_dir / 'archive.mp4'
    directory.mkdir()
    source = directory / 'video.webm'
    write_file(source, 10 * MB)

    def run(command, **kwargs):
        if command[0] == 'ffprobe':
            return subprocess.CompletedProcess(command, 0, '10', '')
        write_file(command[-1], MB)
        return subprocess.CompletedProcess(command, 0, b'', b'')

    monkeypatch.setattr(media.subprocess, 'run', run)

    assert media.split_video(str(source)) == [str(directory / 'video_part1.mp4')]
    assert source.stat().st_size == 10 * MB


@pytest.mark.parametrize('failure', ['exit', 'timeout', 'missing', 'stat'])
def test_failure_removes_finished_and_partial_outputs(download_dir, monkeypatch, failure):
    source = download_dir / 'video.mp4'
    write_file(source, 100 * MB)
    ffmpeg_calls = 0
    original_getsize = os.path.getsize

    def run(command, **kwargs):
        nonlocal ffmpeg_calls
        if command[0] == 'ffprobe':
            return subprocess.CompletedProcess(command, 0, '300', '')
        ffmpeg_calls += 1
        write_file(command[-1], MB)
        if ffmpeg_calls == 2:
            if failure == 'exit':
                raise subprocess.CalledProcessError(1, command, stderr=b'failure')
            if failure == 'timeout':
                raise subprocess.TimeoutExpired(command, 1)
            if failure == 'missing':
                raise FileNotFoundError('ffmpeg unavailable')
        return subprocess.CompletedProcess(command, 0, b'', b'')

    def getsize(path):
        if failure == 'stat' and str(path).endswith('_part2.mp4'):
            raise OSError('cannot stat output')
        return original_getsize(path)

    monkeypatch.setattr(media.subprocess, 'run', run)
    monkeypatch.setattr(media.os.path, 'getsize', getsize)

    assert media.split_video(str(source)) == []
    assert sorted(download_dir.iterdir()) == [source]


def test_exhausted_size_retries_remove_all_outputs(download_dir, monkeypatch):
    source = download_dir / 'video.mp4'
    write_file(source, 100 * MB)

    def run(command, **kwargs):
        if command[0] == 'ffprobe':
            return subprocess.CompletedProcess(command, 0, '300', '')
        size = MB if command[-1].endswith('_part1.mp4') else 55 * MB
        write_file(command[-1], size)
        return subprocess.CompletedProcess(command, 0, b'', b'')

    monkeypatch.setattr(media.subprocess, 'run', run)

    assert media.split_video(str(source)) == []
    assert sorted(download_dir.iterdir()) == [source]


@pytest.mark.parametrize('output', ['nan', 'inf', '-inf', '0', '-10', 'invalid'])
def test_duration_rejects_invalid_values(monkeypatch, output):
    monkeypatch.setattr(
        media.subprocess, 'run',
        lambda command, **kwargs: subprocess.CompletedProcess(command, 0, output, ''),
    )

    assert media._get_video_duration('video.mp4') is None


@pytest.mark.parametrize('failure', ['timeout', 'missing'])
def test_duration_handles_process_failures(monkeypatch, failure):
    def run(command, **kwargs):
        if failure == 'timeout':
            raise subprocess.TimeoutExpired(command, 1)
        raise FileNotFoundError('ffprobe unavailable')

    monkeypatch.setattr(media.subprocess, 'run', run)

    assert media._get_video_duration('video.mp4') is None


def test_external_processes_have_finite_timeouts(download_dir, monkeypatch):
    source = download_dir / 'video.mp4'
    write_file(source, 10 * MB)
    timeouts = []

    def run(command, **kwargs):
        timeouts.append(kwargs.get('timeout'))
        if command[0] == 'ffprobe':
            return subprocess.CompletedProcess(command, 0, '10', '')
        write_file(command[-1], MB)
        return subprocess.CompletedProcess(command, 0, b'', b'')

    monkeypatch.setattr(media.subprocess, 'run', run)

    assert len(media.split_video(str(source))) == 1
    assert len(timeouts) == 2
    assert all(isinstance(value, (int, float)) and 0 < value < 3600 for value in timeouts)


def test_safe_path_uses_current_download_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(media, 'DOWNLOAD_DIR', str(tmp_path))

    assert media.is_safe_path(str(tmp_path / 'video.mp4'))


def test_safe_path_rejects_traversal_and_sibling_prefix(tmp_path):
    base = tmp_path / 'downloads'

    assert media.is_safe_path(str(base / 'video.mp4'), str(base))
    assert not media.is_safe_path(str(base / '..' / 'secret.mp4'), str(base))
    assert not media.is_safe_path(str(tmp_path / 'downloads-other' / 'video.mp4'), str(base))


def test_safe_path_rejects_symlink_escape(download_dir, tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    link = download_dir / 'linked'
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        if os.name != 'nt':
            raise
        # Windows directory junctions do not require symlink privileges.
        import _winapi
        _winapi.CreateJunction(str(outside), str(link))

    assert not media.is_safe_path(str(link / 'video.mp4'), str(download_dir))


def test_cleanup_skips_unsafe_paths_and_continues_after_errors(download_dir, tmp_path, monkeypatch):
    locked = download_dir / 'locked.mp4'
    removable = download_dir / 'removable.mp4'
    outside = tmp_path / 'outside.mp4'
    for path in (locked, removable, outside):
        path.write_bytes(b'video')
    original_remove = os.remove

    def remove(path):
        if str(path) == str(locked):
            raise PermissionError('file is locked')
        original_remove(path)

    monkeypatch.setattr(media.os, 'remove', remove)

    media._cleanup_parts([str(locked), str(outside), str(removable)])

    assert locked.exists()
    assert outside.exists()
    assert not removable.exists()


def test_cleanup_respects_explicit_base_directory(tmp_path):
    owned = tmp_path / 'owned'
    owned.mkdir()
    removable = owned / 'video.mp4'
    outside = tmp_path / 'outside.mp4'
    removable.write_bytes(b'video')
    outside.write_bytes(b'video')

    media._cleanup_parts([str(removable), str(outside)], base_dir=str(owned))

    assert not removable.exists()
    assert outside.exists()
