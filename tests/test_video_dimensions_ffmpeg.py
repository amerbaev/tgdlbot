"""Offline dimension checks with real files, including MP4 display rotation."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import media


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'requires ffmpeg/ffprobe')
class VideoDimensionsFFmpegTests(unittest.TestCase):
    def test_dimensions_match_display_geometry_without_modifying_video(self):
        cases = [
            (640, 360, '1/1', 0, (640, 360)),
            (360, 640, '1/1', 0, (360, 640)),
            (640, 360, '1/1', 90, (360, 640)),
            (640, 360, '1/1', -90, (360, 640)),
            (640, 360, '1/1', 180, (640, 360)),
            (720, 576, '16/15', 0, (768, 576)),
            (720, 576, '16/15', 90, (576, 768)),
        ]
        for width, height, sar, rotation, expected in cases:
            with self.subTest(size=(width, height), sar=sar, rotation=rotation):
                with tempfile.TemporaryDirectory() as directory:
                    source = Path(directory) / 'source.mp4'
                    subprocess.run([
                        'ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        f'color=white:s={width}x{height}:r=1:d=1',
                        '-vf', f'setsar={sar}', '-c:v', 'mpeg4', str(source),
                    ], capture_output=True, check=True, timeout=30)
                    video = source
                    if rotation:
                        video = Path(directory) / 'rotated.mp4'
                        subprocess.run([
                            'ffmpeg', '-v', 'error', '-display_rotation:v:0', str(rotation),
                            '-i', str(source), '-c', 'copy', str(video),
                        ], capture_output=True, check=True, timeout=30)
                    original = video.read_bytes()
                    with patch.object(media, 'DOWNLOAD_DIR', directory):
                        dimensions = media.get_video_dimensions(str(video))
                    self.assertEqual(dimensions, {'width': expected[0], 'height': expected[1]})
                    self.assertEqual(video.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
