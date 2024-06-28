import csv
import json
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path

import settings
from dateutil.parser import parse as parse_date
from lib.formatting import seconds_to_hms
from pytz import timezone

timezone = timezone(settings.TIMEZONE)

VIDEO_MIME_TYPES = {
    '.flv': 'video/x-flv',
    '.mp4': 'video/mp4',
    '.ts': 'video/MP2T',
    '.3gp': 'video/3gpp',
    '.mov': 'video/quicktime',
    '.avi': 'video/x-msvideo',
    '.wmv': 'video/x-ms-wmv',
    '.mpg': 'video/mpeg',
    '.mpeg': 'video/mpeg',
}

METADATA_CSV_HEADERS = [
    'vernon_id',
    'title',
    'filetype',
    'duration_secs',
    'duration_hms',
    'checksum',
    'mime_type',
    'creation_datetime',
    'file_size_bytes',
    'overall_bit_rate',
    'video_codec',
    'video_bit_rate',
    'video_max_bit_rate',
    'video_frame_rate',
    'width',
    'height',
    'audio_codec',
    'audio_channels',
    'audio_sample_rate',
    'audio_bit_rate',
    'audio_max_bit_rate',
]


class FFMPEGError(subprocess.CalledProcessError):
    def __str__(self):
        return f"Command '{' '.join(self.cmd)}' didn't complete successfully (exit status {self.returncode}). "\
               "Perhaps not a valid video file?"


def get_file_metadata(file_location):
    return {
        'creation_datetime': timezone.localize(datetime.fromtimestamp(os.path.getctime(file_location))),
        'modified_datetime': timezone.localize(datetime.fromtimestamp(os.path.getmtime(file_location))),
        'file_size_bytes': os.path.getsize(file_location),
    }


def get_video_metadata(video_location):  # pylint: disable=too-many-locals
    """
    Use ffprobe to discern information about the video.

    :param video_location: URL or Path to video file. URLs that 30x redirect to a file are OK.
    :return: Dictionary of attributes.
    """

    ffprobe_args = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", video_location]
    try:
        command = " ".join(ffprobe_args)
        logging.info("Running %s", command)
        cmd = subprocess.run(ffprobe_args, stdout=subprocess.PIPE, check=True)
        out = cmd.stdout
        m = json.loads(out.decode('utf-8'))
    except subprocess.CalledProcessError as e:
        raise FFMPEGError(e.returncode, ffprobe_args) from e

    # Put the first stream of each type in the top-level, for straightforward property access
    # e.g. j['video']['width']
    for stream in m['streams']:
        if stream['codec_type'] not in m:
            m[stream['codec_type']] = stream

    m_video = m.get('video', {})
    m_audio = m.get('audio', {})

    frame_rate = m_video.get('avg_frame_rate', "0/1").split("/")
    video_frame_rate = int(frame_rate[0]) * 1.0 / int(frame_rate[1])

    # pylint: disable=fixme
    # TODO: these are naive datetimes at the moment. Need to make them aware.
    # Use various techniques to get the creation date. If it's in the video metadata, use that,
    # else use the file/header.

    file_metadata = get_file_metadata(video_location)
    try:
        creation_datetime = parse_date(m['format']['tags'].get('creation_time'))
    except (KeyError, ValueError, TypeError):
        creation_datetime = file_metadata['creation_datetime']

    _, ext = os.path.splitext(video_location)

    with open(f'{video_location}.md5', 'r', encoding='utf-8') as checksum_file:
        checksum = checksum_file.read()

    duration_hms = seconds_to_hms(
        float(m['format'].get('duration', 0.0)),
        always_include_hours=True,
        output_frames=True,
        framerate=video_frame_rate
    )

    return {
        'mime_type': VIDEO_MIME_TYPES.get(ext, None),
        'creation_datetime': str(creation_datetime),
        'file_size_bytes': file_metadata['file_size_bytes'],

        'duration_secs': float(m['format'].get('duration', 0.0)),
        'duration_hms': duration_hms,
        'overall_bit_rate': int(m['format'].get('bit_rate', 0)) or None,

        'video_codec': f"{m_video.get('codec_long_name', None)} ({m_video.get('codec_tag_string', None)})",
        'video_bit_rate': int(m_video.get('bit_rate', 0)) or None,
        'video_max_bit_rate': int(m_video.get('max_bit_rate', 0)) or None,
        'video_frame_rate': video_frame_rate,

        'width': m_video.get('width', None),  # int already
        'height': m_video.get('height', None),  # int already

        'audio_codec': f"{m_audio.get('codec_long_name', None)} ({m_audio.get('codec_tag_string', None)})",
        'audio_channels': m_audio.get('channels', None),  # int
        'audio_sample_rate': int(m_audio.get('sample_rate', 0)) or None,
        'audio_bit_rate': int(m_audio.get('bit_rate', 0)) or None,
        'audio_max_bit_rate': int(m_audio.get('max_bit_rate', 0)) or None,
        'checksum': checksum,
    }


# Mini lib for network-concurrency-friendly locking/unlocking a file by writing adjacent '.lock' files.
def _lockfile(filepath):
    return f"{filepath}.lock"


def is_locked(filepath):
    return os.path.exists(_lockfile(filepath))


def lock(filepath):
    Path(_lockfile(filepath)).touch()


def unlock(filepath):
    os.remove(_lockfile(filepath))


def restricted_file(filepath):
    """
    Prevent files marked RESTRICTED from being transcoded.
    These files are named with ACMIId_fourdigitcode_RESTRICTED_title.
    """
    restricted = False
    if '_RESTRICTED_' in filepath:
        restricted = True
        logging.info('Ignoring restricted file: %s', filepath)
    return restricted


def find_video_file(source_folder, lock_files=True):  # pylint: disable=inconsistent-return-statements
    # generate all the video paths in the source folder
    source_folder = os.path.abspath(os.path.expanduser(source_folder))
    for dirpath, _, filenames in os.walk(source_folder, followlinks=True):
        for file in filenames:
            # pylint: disable=consider-iterating-dictionary
            if os.path.splitext(file)[-1] in list(VIDEO_MIME_TYPES.keys()):
                filepath = os.path.join(dirpath, file)
                # make sure the file still exists, in case another thread is running and deleted it
                if not os.path.exists(filepath):
                    continue
                if restricted_file(filepath):
                    lock(filepath)
                    continue
                if lock_files:
                    if not is_locked(filepath):
                        lock(filepath)
                        return filepath
                else:
                    return filepath


def write_metadata_summary_entry(file_metadata):
    """
    Write an entry in the summary csv file containing metadata from a processed video
    :param file_metadata: the video's metadata
    :param folder: the folder where the csv file is/will be saved
    :return: None
    """
    metadata_file_path = os.path.join(settings.OUTPUT_FOLDER, f'{datetime.today().strftime("%Y%m%d")}_metadata.csv')
    metadata_file_exists = os.path.isfile(metadata_file_path)
    with open(metadata_file_path, 'a', encoding='utf-8') as metadata_csv:
        metadata_csv_writer = csv.DictWriter(metadata_csv, fieldnames=METADATA_CSV_HEADERS)
        if not metadata_file_exists:
            metadata_csv_writer.writeheader()
        metadata_csv_writer.writerow(file_metadata)
