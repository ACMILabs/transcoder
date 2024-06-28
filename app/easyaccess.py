#!/usr/bin/env python3
"""
(Watch a folder for compatible video files.)
For every compatible video file in the watch folder (assume it is a master file):
    - [x] find or create the destination folders in master and access
    - [x] if we don't have a destination access file...
    - [x] convert to access format (h264 output)
    - [x] fixity copy the files to the appropriate destination folders (leave .md5 files behind)
    - [x] move watched files to "done" folder
    - [x] ffprobe the destination files
    - [x] slack a record of what happened.
"""

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time

import settings
from lib.ffmpeg import (find_video_file, get_video_metadata, unlock,
                        write_metadata_summary_entry)
from lib.fixity import fixity_move, generate_file_md5
from lib.formatting import seconds_to_hms
from lib.s3 import upload_to_s3
from lib.slack import (new_file_slack_message, post_slack_exception,
                       post_slack_message)
from lib.xos import get_or_create_xos_stub_video, update_xos_with_final_video

logging.basicConfig(format='%(asctime)s: %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S', level=logging.INFO)


# pylint: disable=too-many-arguments,inconsistent-return-statements
def convert_and_get_metadata(
        source_file_path,
        dest_file_path,
        ffmpeg_base_args,
        vernon_id,
        file_type,
        title,
):
    if os.path.exists(dest_file_path):
        message = 'Cancelling video conversion: ' + dest_file_path + ' already exists.'
        logging.warning(message)
        post_slack_message(message)
        return

    with tempfile.TemporaryDirectory() as tmp_folder:
        tmp_path = os.path.join(tmp_folder, os.path.basename(dest_file_path))
        ffmpeg_args = ['ffmpeg', '-i', source_file_path] + ffmpeg_base_args + [tmp_path]
        cmd_str = ' '.join(ffmpeg_args)
        logging.info('Running %s', cmd_str)
        subprocess.run(ffmpeg_args, check=True)
        fixity_move(tmp_path, dest_file_path, failsafe_folder=None)
        logging.info('Conversion complete: %s', dest_file_path)

    metadata = get_video_metadata(dest_file_path)
    with open(dest_file_path + '.json', 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, default=str)
    metadata.update({'vernon_id': vernon_id, 'filetype': file_type, 'title': title})
    write_metadata_summary_entry(metadata)
    new_file_slack_message('*New file* :hatching_chick:', dest_file_path, seconds_to_hms(metadata['duration_secs']))

    return metadata


def convert_to_exhibition_formats(
        source_file_path,
        access_file_path,
        access_file_type,
        web_file_path,
        web_file_type,
        vernon_id,
        title,
):  # pylint: disable=too-many-arguments
    access_metadata = None
    web_metadata = None
    try:
        logging.info('Converting to exhibitions access format...')
        access_metadata = convert_and_get_metadata(
            source_file_path,
            access_file_path,
            settings.EXHIBITIONS_ACCESS_FFMPEG_ARGS,
            vernon_id,
            access_file_type,
            title,
        )
        logging.info('Converting to exhibitions access format... DONE\n')
        if settings.TRANSCODE_WEB_COPY:
            logging.info('Converting to exhibitions web format...')
            web_metadata = convert_and_get_metadata(
                source_file_path,
                web_file_path,
                settings.EXHIBITIONS_WEB_FFMPEG_ARGS,
                vernon_id,
                web_file_type,
                title,
            )
            logging.info('Converting to exhibitions web format... DONE\n')
    except Exception as exception:  # pylint: disable=broad-exception-caught
        return post_slack_exception(
            f'Could not convert to exhibitions access and web formats: {exception}'
        )
    return access_metadata, web_metadata


def convert_to_collection_formats(
        source_file_path,
        access_file_path,
        access_file_type,
        web_file_path,
        web_file_type,
        vernon_id,
        title,
):  # pylint: disable=too-many-arguments
    access_metadata = None
    web_metadata = None
    try:
        logging.info('Converting to collections access format...')
        access_metadata = convert_and_get_metadata(
            source_file_path,
            access_file_path,
            settings.ACCESS_FFMPEG_ARGS,
            vernon_id,
            access_file_type,
            title,
        )
        logging.info('Converting to collections access format... DONE\n')
        if settings.TRANSCODE_WEB_COPY:
            logging.info('Converting to collections web format...')
            web_metadata = convert_and_get_metadata(
                source_file_path,
                web_file_path,
                settings.WEB_FFMPEG_ARGS,
                vernon_id,
                web_file_type,
                title,
            )
            logging.info('Converting to collections web format... DONE\n')
    except Exception as exception:  # pylint: disable=broad-exception-caught
        return post_slack_exception(
            f'Could not convert to collections access and web formats: {exception}'
        )
    return access_metadata, web_metadata


# pylint: disable=too-many-locals,too-many-return-statements,too-many-branches,too-many-statements
def main():
    # LOOK FOR VIDEO FILES TO CONVERT
    logging.info('Looking for video files to convert...')
    logging.info('settings.WATCH_FOLDER: %s.', settings.WATCH_FOLDER)
    source_file_path = find_video_file(settings.WATCH_FOLDER)
    if not source_file_path:
        logging.info('No files found. Waiting 1hr.\n')
        time.sleep(3600)
        return
    logging.info('source_file_path: %s', source_file_path)
    logging.info('Looking for video files to convert... DONE\n')

    # MAKE SURE WE HAVE THE DESTINATION FOLDERS
    try:
        logging.info('Making sure we have the destination folders...')
        master_filename = os.path.basename(source_file_path)
        master_basename = os.path.splitext(master_filename)[0]
        master_re_match = re.match(r'([a-zA-Z0-9]+)_([ma][a-z]\d\d)_(.+)', master_basename)

        try:
            vernon_id, master_file_type, title = master_re_match.groups()
            assert master_file_type[0] == 'm'
        except Exception:  # pylint: disable=broad-exception-caught
            if os.getenv('FLEXIBLE_MASTER_NAMING', 'False') == 'True':
                vernon_id = ''
                master_file_type = 'm'
                title = master_basename
            else:
                raise ValueError(  # pylint: disable=raise-missing-from
                    f'{master_filename} is not named like a collections preservation master file. '
                    'Consider setting the environment variable FLEXIBLE_MASTER_NAMING=True.'
                )

        access_file_type = f'a{master_file_type[1:]}'
        web_file_type = f'w{master_file_type[1:]}'
        vernon_id_str = vernon_id + '_' if vernon_id else ''
        access_filename = vernon_id_str + access_file_type + '_' + title + settings.ACCESS_FFMPEG_DESTINATION_EXT
        web_filename = vernon_id_str + web_file_type + '_' + title + settings.WEB_FFMPEG_DESTINATION_EXT
        destination_master_folder = settings.MASTER_FOLDER + vernon_id_str + title + '/'
        destination_access_folder = settings.ACCESS_FOLDER + vernon_id_str + title + '/'
        destination_web_folder = settings.WEB_FOLDER + vernon_id_str + title + '/'

        if not os.path.exists(destination_master_folder):
            os.mkdir(destination_master_folder)
        if not os.path.exists(destination_access_folder):
            os.mkdir(destination_access_folder)
        if settings.TRANSCODE_WEB_COPY:
            if not os.path.exists(destination_web_folder):
                os.mkdir(destination_web_folder)

        master_file_path = destination_master_folder + master_filename
        access_file_path = destination_access_folder + access_filename
        web_file_path = destination_web_folder + web_filename

        logging.info('master_file_path: %s', master_file_path)
        logging.info('access_file_path: %s', access_file_path)
        if settings.TRANSCODE_WEB_COPY:
            logging.info('web_file_path: %s', web_file_path)

        logging.info('Making sure we have the destination folders... DONE\n')
    except Exception as exception:  # pylint: disable=broad-exception-caught
        return post_slack_exception(
            'Could not make sure we have the destination folders. '
            f'There may be something funny with the file name: {exception}'
        )

    # HASH MASTER AND LOG METADATA
    try:
        logging.info('Hashing master and logging metadata...')
        generate_file_md5(source_file_path, store=True)
        master_metadata = get_video_metadata(source_file_path)
        master_metadata.update({'vernon_id': vernon_id, 'filetype': master_file_type, 'title': title})
        write_metadata_summary_entry(master_metadata)
        logging.info('Hashing master and logging metadata... DONE\n')
    except Exception as exception:  # pylint: disable=broad-exception-caught
        return post_slack_exception(f"Couldn't hash master and log metadata: {exception}")

    # UPDATE XOS WITH STUB VIDEO
    try:
        logging.info('Getting or creating XOS stub video...')
        asset_id = get_or_create_xos_stub_video({
            'title': f'{master_filename} NOT UPLOADED',
            'master_metadata': master_metadata,
        })
        logging.info('Stub video django ID: %s', asset_id)
        logging.info('Getting or creating XOS stub video... DONE\n')
    except Exception as exception:  # pylint: disable=broad-exception-caught
        return post_slack_exception(f"Couldn't update XOS: {exception}")

    # CONVERT TO ACCESS AND WEB FORMATS
    if settings.EXHIBITIONS_TRANSCODER:
        # Transcoder settings for in-gallery exhibitions videos
        access_metadata, web_metadata = convert_to_exhibition_formats(
            source_file_path,
            access_file_path,
            access_file_type,
            web_file_path,
            web_file_type,
            vernon_id,
            title,
        )
    else:
        # Transcoder settings for collections videos
        access_metadata, web_metadata = convert_to_collection_formats(
            source_file_path,
            access_file_path,
            access_file_type,
            web_file_path,
            web_file_type,
            vernon_id,
            title,
        )

    # MOVE THE SOURCE FILE INTO THE MASTER FOLDER
    try:
        logging.info('Moving the source file into the master folder...')
        fixity_move(source_file_path, master_file_path, failsafe_folder=settings.OUTPUT_FOLDER)
        with open(master_file_path + '.json', 'w', encoding='utf-8') as f:
            json.dump(master_metadata, f, indent=2, default=str)
        new_file_slack_message(
            '*New master file* :movie_camera:', master_file_path, seconds_to_hms(master_metadata['duration_secs'])
        )
        logging.info('Moving the source file into the master folder... DONE\n')
    except Exception as exception:  # pylint: disable=broad-exception-caught
        return post_slack_exception(f"Couldn't move the source file into the master folder: {exception}")

    # UPLOAD THE ACCESS AND WEB FILES TO S3
    try:
        logging.info('Uploading access file to S3...')
        upload_to_s3(access_file_path)
        logging.info('Uploading access file to S3... DONE\n')
        if settings.TRANSCODE_WEB_COPY:
            logging.info('Uploading web file to S3...')
            upload_to_s3(web_file_path)
            shutil.rmtree(destination_web_folder)
            logging.info('Uploading web file to S3... DONE\n')
    except Exception as exception:  # pylint: disable=broad-exception-caught
        return post_slack_exception(f"{exception} Couldn't upload to S3")

    # UPDATE XOS VIDEO URLS AND METADATA
    try:
        logging.info('Updating XOS video urls and metadata...')
        generate_file_md5(master_file_path, store=True)
        xos_asset_data = {
            'title': master_filename,
            'resource': os.path.basename(access_file_path),
            'access_metadata': json.dumps(access_metadata, default=str),
        }
        if settings.TRANSCODE_WEB_COPY:
            xos_asset_data.update({
                'web_resource': os.path.basename(web_file_path),
                'web_metadata': json.dumps(web_metadata, default=str)
            })
        update_xos_with_final_video(asset_id, xos_asset_data)
        logging.info('Updating XOS video urls and metadata... DONE\n')
    except Exception as exception:  # pylint: disable=broad-exception-caught
        return post_slack_exception(f"{exception} Couldn't update XOS video urls and metadata")

    unlock(source_file_path)
    logging.info('=' * 80)


if __name__ == '__main__':
    while True:
        main()
