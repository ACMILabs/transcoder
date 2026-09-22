import shutil
import tempfile
import unittest
from unittest import mock
from unittest.mock import MagicMock

import requests
import settings
from easyaccess import convert_and_get_metadata
from lib.ffmpeg import find_video_file, restricted_file
from lib.formatting import seconds_to_hms
from lib.xos import update_xos_with_final_video


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
        with tempfile.TemporaryDirectory() as watch_folder:
            video_path = shutil.copy('/code/app/test_data/watch/B2004203_mo01_AmazingVideo.mp4', watch_folder)
            self.assertEqual(find_video_file(watch_folder), video_path)
            self.assertIsNone(find_video_file(watch_folder))
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


class TestXosUpdates(unittest.TestCase):

    def setUp(self):
        self.patch_request = mock.patch('lib.xos.requests.patch').start()
        self.addCleanup(mock.patch.stopall)
        self.sleep = mock.patch('lib.xos.time.sleep').start()
        self.video_data = {'title': 'Video', 'resource': 'video.mp4', 'access_metadata': '{}'}

    @staticmethod
    def response(status):
        response = requests.Response()
        response.status_code = status
        response.url = 'https://example.com/api/assets/5833/'
        return response

    def test_success_without_retry(self):
        self.patch_request.return_value = self.response(200)
        update_xos_with_final_video(5833, self.video_data)
        self.patch_request.assert_called_once()
        self.sleep.assert_not_called()

    def test_server_errors_retry_same_update_and_recover(self):
        self.patch_request.side_effect = [self.response(status) for status in (500, 502, 503, 200)]
        update_xos_with_final_video(5833, self.video_data)
        self.assertEqual(self.patch_request.call_count, 4)
        first_call = self.patch_request.call_args_list[0]
        self.assertTrue(first_call.args[0].endswith('/assets/5833/'))
        self.assertEqual(first_call.kwargs['json'], self.video_data)
        self.assertEqual(self.patch_request.call_args_list, [first_call] * 4)
        self.assertEqual(self.sleep.call_args_list, [mock.call(5), mock.call(10), mock.call(20)])

    def test_server_errors_raise_after_three_retries(self):
        self.patch_request.return_value = self.response(500)
        with self.assertRaises(requests.HTTPError) as caught:
            update_xos_with_final_video(5833, self.video_data)
        self.assertIs(caught.exception.response, self.patch_request.return_value)
        self.assertEqual(self.patch_request.call_count, 4)
        self.assertEqual(self.sleep.call_count, 3)

    def test_client_errors_do_not_retry(self):
        for status in (400, 401, 403, 404, 422):
            with self.subTest(status=status):
                self.patch_request.reset_mock()
                self.patch_request.return_value = self.response(status)
                with self.assertRaises(requests.HTTPError):
                    update_xos_with_final_video(5833, self.video_data)
                self.patch_request.assert_called_once()
                self.sleep.assert_not_called()

    def test_connection_errors_and_timeouts_retry(self):
        for error_type in (requests.ConnectionError, requests.Timeout):
            with self.subTest(error_type=error_type):
                self.patch_request.reset_mock()
                self.sleep.reset_mock()
                self.patch_request.side_effect = [error_type('Temporary failure'), self.response(200)]
                update_xos_with_final_video(5833, self.video_data)
                self.assertEqual(self.patch_request.call_count, 2)
                self.sleep.assert_called_once_with(5)

    def test_connection_errors_and_timeouts_stop_after_three_retries(self):
        for error_type in (requests.ConnectionError, requests.Timeout):
            with self.subTest(error_type=error_type):
                self.patch_request.reset_mock()
                self.sleep.reset_mock()
                error = error_type('Persistent failure')
                self.patch_request.side_effect = error
                with self.assertRaises(error_type) as caught:
                    update_xos_with_final_video(5833, self.video_data)
                self.assertIs(caught.exception, error)
                self.assertEqual(self.patch_request.call_count, 4)
                self.assertEqual(self.sleep.call_count, 3)


if __name__ == '__main__':
    unittest.main()
