"""Offline splitting regressions, also runnable with unittest in production."""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import media


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'requires ffmpeg/ffprobe')
class VideoSplitFFmpegTests(unittest.TestCase):
    def run_ffmpeg(self, *arguments, **kwargs):
        return subprocess.run(
            ['ffmpeg', '-nostdin', '-v', 'error', *map(str, arguments)],
            capture_output=True, check=True, timeout=30, **kwargs,
        )

    def frame_count(self, path):
        result = subprocess.run([
            'ffprobe', '-v', 'error', '-select_streams', 'v:0', '-count_frames',
            '-show_entries', 'stream=nb_read_frames', '-of', 'csv=p=0', str(path),
        ], capture_output=True, text=True, check=True, timeout=30)
        return int(result.stdout)

    def make_numbered_video(self, path, *, frames=125, rate='25', codec='mpeg4',
                            gop=25, bframes=0, audio=False, variable_rate=False):
        # Eight wide black/white stripes encode the frame number. Unlike pixel
        # hashes, these IDs survive lossy encoding and still expose duplicates.
        pixels = b''.join(
            bytes(235 if number & (1 << (x // 16)) else 16 for x in range(128)) * 64
            for number in range(frames)
        )
        args = ['-f', 'rawvideo', '-pixel_format', 'gray', '-video_size', '128x64',
                '-framerate', rate, '-i', 'pipe:0']
        if audio:
            args += ['-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=5']
        if variable_rate:
            args += ['-vf', r'select=not(eq(mod(n\,3)\,1))']
        args += ['-c:v', codec, '-g', str(gop), '-bf', str(bframes),
                 '-pix_fmt', 'yuv420p', '-fps_mode', 'passthrough']
        if codec == 'libx264':
            args += ['-x264-params', 'scenecut=0']
        if audio:
            args += ['-c:a', 'aac']
        self.run_ffmpeg(*args, path, input=pixels)

    def frame_ids(self, path):
        result = self.run_ffmpeg(
            '-i', path, '-map', '0:v:0', '-fps_mode', 'passthrough',
            '-f', 'rawvideo', '-pix_fmt', 'gray', 'pipe:1',
        )
        frame_size = 128 * 64
        self.assertEqual(len(result.stdout) % frame_size, 0)
        return [
            sum((result.stdout[offset + 32 * 128 + bit * 16 + 8] > 128) << bit
                for bit in range(8))
            for offset in range(0, len(result.stdout), frame_size)
        ]

    def test_non_keyframe_cut_keeps_all_125_frames_within_size_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.mp4'
            self.run_ffmpeg(
                '-f', 'lavfi', '-i', 'testsrc2=s=640x360:r=25:d=5',
                '-c:v', 'mpeg4', '-g', '25', '-q:v', '3', source,
            )
            original = source.read_bytes()
            limit = source.stat().st_size * 2 // 3
            with patch.object(media, 'DOWNLOAD_DIR', directory), \
                    patch.object(media, 'MAX_FILE_SIZE', limit):
                parts = media.split_video(str(source))
            self.assertGreaterEqual(len(parts), 2)
            self.assertTrue(all(0 < Path(part).stat().st_size <= limit for part in parts))
            self.assertEqual(self.frame_count(source), 125)
            self.assertEqual(sum(self.frame_count(part) for part in parts), 125)
            self.assertEqual(source.read_bytes(), original)

    def test_every_frame_appears_once_in_order_across_boundaries(self):
        cases = [
            {'gop': 1},
            {'gop': 25},
            {'codec': 'libx264', 'gop': 250, 'bframes': 3, 'audio': True},
            {'codec': 'libx264', 'gop': 250, 'bframes': 3, 'rate': '30000/1001'},
            {'frames': 126},  # One-frame final part.
            {'codec': 'libx264', 'variable_rate': True},
        ]
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                suffix = '.mkv' if case.get('variable_rate') else '.mp4'
                source = Path(directory) / f'source{suffix}'
                self.make_numbered_video(source, **case)
                expected = list(range(case.get('frames', 125)))
                if case.get('variable_rate'):
                    expected = [number for number in expected if number % 3 != 1]
                self.assertEqual(self.frame_ids(source), expected)
                with patch.object(media, 'DOWNLOAD_DIR', directory), \
                        patch.object(media, '_calculate_parts', return_value=(2, 2.5)):
                    parts = media.split_video(str(source))
                self.assertGreaterEqual(len(parts), 2)
                actual = []
                for part in parts:
                    ids = self.frame_ids(part)
                    self.assertTrue(ids, 'Every part must contain decodable video')
                    actual.extend(ids)
                    if case.get('audio'):
                        result = subprocess.run([
                            'ffprobe', '-v', 'error', '-show_streams', '-of', 'json', part,
                        ], capture_output=True, text=True, check=True, timeout=30)
                        streams = json.loads(result.stdout)['streams']
                        audio = next(s for s in streams if s['codec_type'] == 'audio')
                        video = next(s for s in streams if s['codec_type'] == 'video')
                        self.assertLess(abs(float(audio['duration']) - float(video['duration'])), 0.1)
                        self.assertLess(abs(float(audio['start_time']) - float(video['start_time'])), 0.1)
                self.assertEqual(actual, expected)

    def test_retry_fits_parts_when_reencoding_increases_bitrate(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'compressed.mp4'
            self.run_ffmpeg(
                '-f', 'lavfi', '-i', 'testsrc2=s=640x360:r=25:d=5',
                '-c:v', 'libx264', '-crf', '35', source,
            )
            original = source.read_bytes()
            limit = source.stat().st_size * 2 // 3
            with patch.object(media, 'DOWNLOAD_DIR', directory), \
                    patch.object(media, 'MAX_FILE_SIZE', limit):
                parts = media.split_video(str(source))
            self.assertGreater(len(parts), 2)
            self.assertTrue(all(0 < Path(part).stat().st_size <= limit for part in parts))
            self.assertEqual(sum(self.frame_count(part) for part in parts), 125)
            self.assertEqual(source.read_bytes(), original)

    def test_fractional_boundaries_do_not_round_frames_into_both_parts(self):
        for duration in (1.01, 5 / 3):
            with self.subTest(duration=duration), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / 'source.mp4'
                self.make_numbered_video(source, codec='libx264', gop=250, bframes=3)
                with patch.object(media, 'DOWNLOAD_DIR', directory), \
                        patch.object(media, '_calculate_parts', return_value=(5, duration)):
                    parts = media.split_video(str(source))
                self.assertTrue(parts)
                self.assertEqual(
                    [frame for part in parts for frame in self.frame_ids(part)],
                    list(range(125)),
                )

    def test_size_retry_keeps_all_frames_including_short_tail(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.mp4'
            self.make_numbered_video(source, codec='libx264', gop=250, bframes=3)
            getsize = media.os.path.getsize
            rejected = False

            def size(path):
                nonlocal rejected
                if str(path).endswith('_part1.mp4') and not rejected:
                    rejected = True
                    return media.MAX_FILE_SIZE + 1
                return getsize(path)

            with patch.object(media, 'DOWNLOAD_DIR', directory), \
                    patch.object(media, '_calculate_parts', return_value=(2, 2.5)), \
                    patch.object(media.os.path, 'getsize', side_effect=size):
                parts = media.split_video(str(source))
            self.assertTrue(rejected)
            self.assertEqual(len(parts), 3)
            self.assertEqual([frame for part in parts for frame in self.frame_ids(part)], list(range(125)))


if __name__ == '__main__':
    unittest.main()
