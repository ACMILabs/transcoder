import logging
import os
import time

import requests

XOS_AUTH_TOKEN = os.environ['XOS_AUTH_TOKEN']
XOS_API_ENDPOINT = os.environ['XOS_API_ENDPOINT']


def get_or_create_xos_stub_video(video_data):
    """
    Creates and returns the ID of a stub video with keys and values from video_data.
    If one already exists due to a previously failed transcoding, just returns its ID.
    """
    xos_video_endpoint = f'{XOS_API_ENDPOINT}assets/'
    headers = {'Authorization': f'Token {XOS_AUTH_TOKEN}'}

    get_response = requests.get(
        f"{xos_video_endpoint}?title_contains=NOT%20UPLOADED&checksum={video_data['master_metadata']['checksum']}",
        headers=headers,
        timeout=120,
    )
    get_response.raise_for_status()
    get_response_json = get_response.json()
    if get_response_json['count'] == 1:
        return get_response_json['results'][0]['id']

    response = requests.post(xos_video_endpoint, json=video_data, headers=headers, timeout=120)
    response.raise_for_status()
    return response.json()['id']


def update_xos_with_final_video(asset_id, video_data):
    """
    Update the asset, retrying server and connection errors three times.
    """
    xos_video_endpoint = f'{XOS_API_ENDPOINT}assets/{asset_id}/'
    headers = {'Authorization': f'Token {XOS_AUTH_TOKEN}'}
    retry_delays = (5, 10, 20)
    for attempt in range(len(retry_delays) + 1):
        try:
            response = requests.patch(xos_video_endpoint, json=video_data, headers=headers, timeout=120)
            response.raise_for_status()
            return
        except requests.HTTPError as exception:
            if exception.response is None or not 500 <= exception.response.status_code < 600:
                raise
            if attempt == len(retry_delays):
                raise
        except (requests.ConnectionError, requests.Timeout):
            if attempt == len(retry_delays):
                raise
        delay = retry_delays[attempt]
        logging.warning(
            'Could not update XOS asset %s; retry %s/%s in %s seconds.',
            asset_id, attempt + 1, len(retry_delays), delay,
        )
        time.sleep(delay)
