import os
import logging

import boto3

S3_BUCKET = os.environ['S3_BUCKET']
S3_ACCESS_KEY = os.environ['S3_ACCESS_KEY']
S3_SECRET_KEY = os.environ['S3_SECRET_KEY']
S3_LOCATION = os.environ['S3_LOCATION']

def upload_to_s3(path):
    """
    Takes a relative or absolute path to a file and uploads it to s3.
    """
    client = boto3.client(
        's3',
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY
    )

    # TODO: turn off crazy verbose boto3 logs

    basename = os.path.basename(path)
    logging.info("Uploading to S3: %s", basename)
    client.upload_file(path, S3_BUCKET, S3_LOCATION+'/'+basename)
    logging.info("Finished uploading to S3: %s", basename)
