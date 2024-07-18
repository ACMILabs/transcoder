import os

# These paths are mounted into the docker container by docker-entrypoint.sh
WATCH_FOLDER = "/mount/watch/"
MASTER_FOLDER = "/mount/master/"
ACCESS_FOLDER = "/mount/access/"
WEB_FOLDER = "/tmp/"
OUTPUT_FOLDER = "/mount/output/"

ACCESS_FFMPEG_DESTINATION_EXT = ".mp4"
ACCESS_FFMPEG_ARGS = [
    '-loglevel', 'panic',
    '-stats',
    '-hide_banner',
    '-pix_fmt', 'yuv420p',  # colour format compatible with quicktime
    '-c:v', 'libx264',
    '-preset', 'veryslow',
    # quality of conversion. Try veryslow if lots of time, or ultrafast for testing. Default is 'medium'.
    '-crf', '23',  # compression (implies bitrate): 23 is default, 18 is visually lossless
    '-c:a', 'aac',  # convert audio to aac
    '-n',  # don't overwrite existing files
]

WEB_FFMPEG_DESTINATION_EXT = ".mp4"
WEB_FFMPEG_ARGS = [
    '-loglevel', 'panic',
    '-stats',
    '-hide_banner',
    '-pix_fmt', 'yuv420p',  # colour format compatible with quicktime
    '-c:v', 'libx264',
    '-preset', 'veryslow',
    # quality of conversion. Try veryslow if lots of time, or ultrafast for testing. Default is 'medium'.
    '-crf', '28',  # compression (implies bitrate): 23 is default, 18 is visually lossless
    '-c:a', 'aac',  # convert audio to aac
    '-n',  # don't overwrite existing files
]

EXHIBITIONS_ACCESS_FFMPEG_ARGS = [
    '-loglevel', 'panic',
    '-stats',
    '-hide_banner',
    '-pix_fmt', 'yuv420p',  # colour format compatible with quicktime
    '-c:v', 'libx264',
    '-b:v', os.getenv('EXHIBITIONS_BITRATE', '20000k'),  # video bitrate
    '-minrate', os.getenv('EXHIBITIONS_BITRATE', '20000k'),
    '-maxrate', os.getenv('EXHIBITIONS_BITRATE', '20000k'),
    '-bufsize', os.getenv('EXHIBITIONS_BITRATE', '20000k'),
    '-nal-hrd', 'cbr',  # ensure h264 uses a constant bitrate for encoding
    '-vf', f'scale={os.getenv("EXHIBITIONS_VIDEO_SIZE", "1920:1080")}:force_original_aspect_ratio=decrease,'
           f'pad={os.getenv("EXHIBITIONS_VIDEO_SIZE", "1920:1080")}:-1:-1:color=black',  # output video size
    '-r', os.getenv('EXHIBITIONS_FRAMERATE', '25'),  # output video framerate
    '-c:a', 'aac',  # convert audio to aac
    '-ab', '320k',  # audio bitrate
    '-ac', '2',  # audio number of channels
    '-ar', '48000',  # audio sample rate
    '-n',  # don't overwrite existing files
]

EXHIBITIONS_WEB_FFMPEG_ARGS = [
    '-loglevel', 'panic',
    '-stats',
    '-hide_banner',
    '-pix_fmt', 'yuv420p',  # colour format compatible with quicktime
    '-c:v', 'libx264',
    '-vf', f'scale={os.getenv("EXHIBITIONS_VIDEO_SIZE", "1920:1080")}:force_original_aspect_ratio=decrease,'
           f'pad={os.getenv("EXHIBITIONS_VIDEO_SIZE", "1920:1080")}:-1:-1:color=black',  # output video size
    '-r', os.getenv('EXHIBITIONS_FRAMERATE', '25'),  # output video framerate
    '-preset', 'veryslow',
    # quality of conversion. Try veryslow if lots of time, or ultrafast for testing. Default is 'medium'.
    '-crf', '28',  # compression (implies bitrate): 23 is default, 18 is visually lossless
    '-c:a', 'aac',  # convert audio to aac
    '-ab', '320k',  # audio bitrate
    '-ac', '2',  # audio number of channels
    '-ar', '48000',  # audio sample rate
    '-n',  # don't overwrite existing files
]

TIMEZONE = 'Australia/Victoria'

# for retries when copying files between volumes fail
MOVE_RETRIES = 5
RETRY_WAIT = 300  # five minutes

MASTER_URL = "smb:" + os.getenv('SMB_MASTER', "//fsqcollnas.corp.acmi.net.au/Preservation%20Masters/")
ACCESS_URL = "smb:" + os.getenv('SMB_ACCESS', "//fsqcollnas.corp.acmi.net.au/Access%20Copies/")
WEB_URL = "smb:" + os.getenv('SMB_WEB', "//fsqcollnas.corp.acmi.net.au/Web%20Copies/")

TRANSCODE_WEB_COPY = os.getenv('TRANSCODE_WEB_COPY', 'False') == 'True'

EXHIBITIONS_TRANSCODER = os.getenv('EXHIBITIONS_TRANSCODER', 'False') == 'True'
