"""Compare offline splitting against a Git revision; no bot or network calls.

Example: uv run python benchmarks/benchmark_split.py --base-ref c81b85c \
    --rounds 3 --output /tmp/tgdlbot-split.json
Generated media and split files live only in a temporary directory.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import logging
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
os.environ['TELEGRAM_BOT_TOKEN'] = '000000:offline-benchmark'
logging.disable(logging.CRITICAL)
MB = 1024 * 1024
CASES = ['landscape', 'portrait', 'no_retry', 'concurrent', 'full_limit']


def run(*args):
    return subprocess.run(list(map(str, args)), capture_output=True, check=True, timeout=600).stdout


def probe(path):
    return json.loads(run(
        'ffprobe', '-v', 'error', '-count_frames', '-show_streams', '-of', 'json', path,
    ))['streams']


def make_source(directory, case):
    path = directory / 'source.mp4'
    width, height = (720, 1280) if case == 'portrait' else (1280, 720)
    graph = f'testsrc2=s={width}x{height}:r=30:d=12'
    codec = ['-c:v', 'libx264', '-preset', 'fast', '-crf', '35']
    if case == 'no_retry':
        codec = ['-c:v', 'mpeg4', '-q:v', '3']
    if case == 'full_limit':
        # A deterministic 144-second, >50 MiB source, without a long fixture
        # generation encode. Repetition is a benchmark limitation, not real footage.
        seed = directory / 'seed.mp4'
        run('ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
            'testsrc2=s=1920x1080:r=30:d=6,noise=alls=20:allf=t+u:all_seed=42',
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '30', '-y', seed)
        run('ffmpeg', '-nostdin', '-v', 'error', '-stream_loop', '23', '-i', seed,
            '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=144',
            '-c:v', 'copy', '-c:a', 'aac', '-shortest', '-movflags', '+faststart', '-y', path)
        assert path.stat().st_size > 50 * MB
    else:
        run('ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', graph,
            '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=12',
            *codec, '-c:a', 'aac', '-movflags', '+faststart', '-y', path)
    return path


def split(source, module_text, limit):
    module = types.ModuleType('measured_media')
    exec(compile(module_text, 'media.py', 'exec'), module.__dict__)
    module.DOWNLOAD_DIR = str(source.parent)
    module.MAX_FILE_SIZE = limit
    encode = module._create_video_part
    attempts = []

    def measured(path, output, start, duration):
        begin = time.perf_counter()
        ok = encode(path, output, start, duration)
        attempts.append({'start': start, 'duration': duration,
                         'seconds': time.perf_counter() - begin,
                         'bytes': Path(output).stat().st_size if ok else 0})
        return ok

    module._create_video_part = measured
    begin = time.perf_counter()
    parts = module.split_video(str(source))
    seconds = time.perf_counter() - begin
    assert parts, 'Split failed'
    assert all(0 < Path(part).stat().st_size <= limit for part in parts)
    return {'seconds': seconds, 'attempts': attempts, 'parts': parts}


def verify_and_clean(result, expected):
    frames = 0
    source_video = next(stream for stream in expected if stream['codec_type'] == 'video')
    for part in result['parts']:
        streams = probe(part)
        video = next(stream for stream in streams if stream['codec_type'] == 'video')
        audio = next(stream for stream in streams if stream['codec_type'] == 'audio')
        assert video['codec_name'] == 'h264' and audio['codec_name'] == 'aac'
        assert (video['width'], video['height']) == (source_video['width'], source_video['height'])
        assert abs(float(video['duration']) - float(audio['duration'])) < 0.15
        frames += int(video['nb_read_frames'])
        Path(part).unlink()
    assert frames == int(source_video['nb_read_frames']), (frames, source_video['nb_read_frames'])
    result['frames'] = frames
    result['parts'] = len(result['parts'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-ref', required=True, help='Git revision containing baseline media.py')
    parser.add_argument('--rounds', type=int, default=3)
    parser.add_argument('--case', action='append', choices=CASES)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.rounds < 1:
        parser.error('--rounds must be positive')
    baseline_sha = run('git', '-C', ROOT, 'rev-parse', args.base_ref).decode().strip()
    sources = {
        'before': run('git', '-C', ROOT, 'show', f'{baseline_sha}:media.py').decode(),
        'after': (ROOT / 'media.py').read_text(),
    }
    report = {'base_sha': baseline_sha, 'candidate_media_sha256': hashlib.sha256(
        sources['after'].encode()).hexdigest(), 'python': platform.python_version(),
        'machine': platform.machine(), 'cpus': os.cpu_count(),
        'ffmpeg': run('ffmpeg', '-version').decode().splitlines()[0], 'runs': []}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='tgdlbot-split-benchmark-') as temporary:
        root = Path(temporary)
        for case in args.case or CASES:
            directory = root / case
            directory.mkdir()
            source = make_source(directory, case)
            expected = probe(source)
            original_hash = hashlib.sha256(source.read_bytes()).digest()
            limit = 50 * MB if case == 'full_limit' else source.stat().st_size * 2 // 3
            jobs = [source]
            if case == 'concurrent':
                for index in range(1, 3):
                    job = directory / str(index)
                    job.mkdir()
                    jobs.append(Path(shutil.copy2(source, job / 'source.mp4')))
            for round_index in range(args.rounds):
                order = ['before', 'after'] if round_index % 2 == 0 else ['after', 'before']
                for mode in order:
                    print(f'Starting {case}, round {round_index + 1}, {mode}', flush=True)
                    begin = time.perf_counter()
                    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
                        results = list(pool.map(lambda path: split(path, sources[mode], limit), jobs))
                    elapsed = time.perf_counter() - begin
                    # Decoding validation is intentionally outside the timed interval.
                    for result in results:
                        verify_and_clean(result, expected)
                    assert hashlib.sha256(source.read_bytes()).digest() == original_hash
                    row = {'case': case, 'round': round_index + 1, 'mode': mode,
                           'seconds': elapsed, 'source_bytes': source.stat().st_size,
                           'limit_bytes': limit, 'jobs': results}
                    report['runs'].append(row)
                    args.output.write_text(json.dumps(report, indent=2) + '\n')
                    print(json.dumps({key: value for key, value in row.items() if key != 'jobs'}), flush=True)
    for case in args.case or CASES:
        medians = {mode: statistics.median(row['seconds'] for row in report['runs']
            if row['case'] == case and row['mode'] == mode) for mode in sources}
        print(f'{case}: {medians["before"]:.3f}s -> {medians["after"]:.3f}s '
              f'({(1 - medians["after"] / medians["before"]) * 100:.1f}% faster)', flush=True)


if __name__ == '__main__':
    main()
