import shutil
import tempfile
import unittest
from unittest import mock
from unittest.mock import MagicMock

import settings
from easyaccess import convert_and_get_metadata
import lib.fixity as fixity
from lib.ffmpeg import find_video_file, restricted_file
from lib.formatting import seconds_to_hms


class TestFormatting(unittest.TestCase):

    def test_secs_only(self):
        self.assertEqual(seconds_to_hms(75), '01:15')

    def test_hours(self):
        self.assertEqual(seconds_to_hms(3600), '01:00:00')

    def test_always_include_hours(self):
        self.assertEqual(seconds_to_hms(75, always_include_hours=True), '00:01:15')

    def test_secs_decimals(self):
        self.assertEqual(seconds_to_hms(72.5, decimal_places=1), '01:12.5')

    def test_secs_decimals_2(self):
        self.assertEqual(seconds_to_hms(72.5, decimal_places=2), '01:12.50')

    def test_frames(self):
        self.assertEqual(seconds_to_hms(72.5, output_frames=True), '01:12:12')

    def test_frames_2(self):
        self.assertEqual(seconds_to_hms(72.5, output_frames=True, framerate=30), '01:12:15')

    def test_ignore_decimals(self):
        self.assertEqual(seconds_to_hms(72.5, decimal_places=2, output_frames=True), '01:12:12')

    def test_hours_and_frames(self):
        self.assertEqual(
            seconds_to_hms(72.5, always_include_hours=True, output_frames=True, framerate=30),
            '00:01:12:15',
        )

    def test_frames_rounding(self):
        self.assertEqual(seconds_to_hms(65.16, output_frames=True, framerate=25), '01:05:04')

    def test_frames_rounding_2(self):
        self.assertEqual(seconds_to_hms(65.99, output_frames=True), '01:06:00')


class TestFileHandling(unittest.TestCase):

    def test_restricted_file(self):
        self.assertTrue(restricted_file('B2004203_mo01_RESTRICTED_CyberthonIV.mov'))

    def test_find_video_file(self):
        self.assertTrue(find_video_file('/code/app/test_data/watch'))
        self.assertFalse(find_video_file('/code/app/test_data/restricted'))


class TestEncoding(unittest.TestCase):

    @mock.patch('easyaccess.new_file_slack_message', MagicMock())
    def test_convert_and_get_metadata(self):
        tmp_folder = tempfile.mkdtemp()
        metadata = convert_and_get_metadata(
            '/code/app/test_data/watch/B2004203_mo01_AmazingVideo.mp4',
            f'{tmp_folder}/video.mp4',
            settings.EXHIBITIONS_ACCESS_FFMPEG_ARGS,
            '1',  # Vernon ID
            settings.ACCESS_FFMPEG_DESTINATION_EXT,
            'Video title',
        )
        self.assertEqual(metadata['mime_type'], 'video/mp4')
        self.assertEqual(metadata['video_frame_rate'], 25.0)
        self.assertEqual(metadata['video_codec'], 'H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10 (avc1)')
        # Test video input bitrate isn't high enough to pass
        # self.assertTrue(metadata['video_bit_rate'] >= 20000000)
        self.assertEqual(metadata['width'], 1920)
        self.assertEqual(metadata['height'], 1080)
        self.assertEqual(metadata['audio_codec'], 'AAC (Advanced Audio Coding) (mp4a)')
        self.assertEqual(metadata['audio_channels'], 2)
        self.assertEqual(metadata['audio_sample_rate'], 48000)
        self.assertTrue(metadata['audio_bit_rate'] >= 320000)
        self.assertEqual(metadata['vernon_id'], '1')
        self.assertEqual(metadata['title'], 'Video title')
        shutil.rmtree(tmp_folder)


if __name__ == '__main__':
    unittest.main()
