import logging
import os
import traceback

import settings
import slack


def post_slack_message(message, channel=None, **kwargs):
    if channel is None:
        channel = os.getenv('SLACK_CHANNEL')

    slack_token = os.getenv('SLACK_TOKEN')

    slack_client = slack.WebClient(token=slack_token)

    response = None
    try:
        response = slack_client.chat_postMessage(
            channel=channel,
            text=message,
            as_user=True,
            **kwargs,  # e.g. attachments
        )
    except slack.errors.SlackApiError as exception:
        response = exception
        logging.error('Error posting to Slack channel %s: %s', channel, exception)

    return response


def slack_link(url, text=''):
    """
    Return a slack-formatted URL of <path|text>.
    """
    if text:
        return f'<{url}|{text}>'
    return f'<{url}>'


def new_file_slack_message(message, file_path, duration):
    # Post a link to a folder/file with an SMB mount.
    if file_path.startswith(settings.MASTER_FOLDER):
        url = file_path.replace(settings.MASTER_FOLDER, settings.MASTER_URL)
    elif file_path.startswith(settings.ACCESS_FOLDER):
        url = file_path.replace(settings.ACCESS_FOLDER, settings.ACCESS_URL)
    elif file_path.startswith(settings.WEB_FOLDER):
        url = file_path.replace(settings.WEB_FOLDER, settings.WEB_URL)
    else:
        raise ValueError(
            f"{file_path} doesn't seem to be in either the Master, Access or Web folders. "
            'Not sure how to make a URL for this.'
        )

    dirname = os.path.dirname(url)
    attachments = [
        {
            'fallback': f'Open folder at {dirname}',
            'actions': [
                {
                    'type': 'button',
                    'text': 'View file :cinema:',
                    'url': url,
                    'style': 'primary'  # or danger
                },
                {
                    'type': 'button',
                    'text': 'Open folder :open_file_folder:',
                    'url': dirname,
                },
            ]
        }
    ]

    formatted_message = f'{message}: {os.path.basename(url)} (Duration {duration})'
    post_slack_message(formatted_message, attachments=attachments)


def post_slack_exception(message):
    traceback.print_exc()
    post_slack_message(message)
