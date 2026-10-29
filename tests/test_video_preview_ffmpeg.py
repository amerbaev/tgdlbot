"""Offline checks with real ffmpeg; also runnable with unittest in production."""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import media


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'requires ffmpeg/ffprobe')
class VideoPreviewFFmpegTests(unittest.TestCase):
    def test_skips_black_intro_and_preserves_landscape_and_portrait(self):
        for width, height in ((640, 360), (360, 640)):
            with self.subTest(size=(width, height)), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / 'video.mp4'
                graph = (
                    f'color=black:s={width}x{height}:r=10:d=2[black];'
                    f'color=white:s={width}x{height}:r=10:d=1[white];'
                    '[black][white]concat=n=2:v=1:a=0'
                )
                self.make_video(source, graph)
                with patch.object(media, 'DOWNLOAD_DIR', directory):
                    preview = media.create_video_preview(str(source))
                self.check_preview(preview, width > height)
                self.assertEqual(list(Path(directory).iterdir()), [source])

    def test_subsecond_video_has_preview(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'short.mp4'
            self.make_video(source, 'color=white:s=640x360:r=10:d=0.1')
            with patch.object(media, 'DOWNLOAD_DIR', directory):
                preview = media.create_video_preview(str(source))
            self.check_preview(preview, landscape=True)

    def test_all_black_video_does_not_supply_black_preview(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'black.mp4'
            self.make_video(source, 'color=black:s=640x360:r=10:d=1')
            with patch.object(media, 'DOWNLOAD_DIR', directory):
                self.assertIsNone(media.create_video_preview(str(source)))

    def test_prefers_source_webp_cover_over_black_video(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'video.mp4'
            self.make_video(source, 'color=black:s=640x360:r=10:d=1')
            cover = Path(str(source) + '.cover')
            subprocess.run([
                'ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=white:s=1280x720',
                '-frames:v', '1', '-c:v', 'libwebp', '-f', 'image2', str(cover),
            ], capture_output=True, check=True, timeout=30)
            with patch.object(media, 'DOWNLOAD_DIR', directory):
                self.check_preview(media.create_video_preview(str(source)), landscape=True)

    def test_broken_cover_falls_back_to_video(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'video.mp4'
            self.make_video(source, 'color=white:s=640x360:r=10:d=1')
            Path(str(source) + '.cover').write_bytes(b'broken cover')
            with patch.object(media, 'DOWNLOAD_DIR', directory):
                self.check_preview(media.create_video_preview(str(source)), landscape=True)

    def make_video(self, source, graph):
        subprocess.run([
            'ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', graph,
            '-c:v', 'mpeg4', '-y', str(source),
        ], capture_output=True, check=True, timeout=30)

    def check_preview(self, preview, landscape):
        self.assertIsNotNone(preview)
        self.assertTrue(preview.startswith(b'\xff\xd8'))
        self.assertLess(len(preview), 200 * 1024)
        result = subprocess.run([
            'ffprobe', '-v', 'error', '-show_entries', 'stream=codec_name,width,height',
            '-of', 'json', '-i', 'pipe:0',
        ], input=preview, capture_output=True, check=True, timeout=30)
        stream = json.loads(result.stdout)['streams'][0]
        self.assertEqual(stream['codec_name'], 'mjpeg')
        self.assertEqual((stream['width'], stream['height']), (320, 180) if landscape else (180, 320))
        result = subprocess.run([
            'ffmpeg', '-v', 'error', '-i', 'pipe:0', '-f', 'rawvideo',
            '-pix_fmt', 'gray', 'pipe:1',
        ], input=preview, capture_output=True, check=True, timeout=30)
        self.assertGreater(sum(result.stdout) / len(result.stdout), 200, 'preview must be white, not black')


if __name__ == '__main__':
    unittest.main()
