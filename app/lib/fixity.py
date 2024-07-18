import hashlib
import logging
import os
import shutil
import time

import settings


def post_move_filename(source_file, dest):
    """Take the filename from the first part and append it to the folder name from the second part. The result is the
    name a file would get after it is moved - allowing us to test for its prior existence."""
    source_filename = os.path.basename(source_file)

    dest_is_file = False

    if os.path.exists(dest):
        if not os.path.isdir(dest):
            dest_is_file = True
    else:  # destination doesn't exist. Let's see if it looks like a file name
        dest_base = os.path.basename(dest)
        if '.' in dest_base and dest_base[-1] != os.sep:
            dest_is_file = True

    if dest_is_file:
        return dest
    return os.path.join(dest, source_filename)


def generate_file_md5(filename, blocksize=2 ** 20, store=False):
    m = hashlib.md5()
    with open(os.path.join(filename), 'rb') as f:
        while True:
            buf = f.read(blocksize)
            if not buf:
                break
            m.update(buf)
    digest = m.hexdigest()

    if store:
        with open(f'{filename}.md5', 'w', encoding='utf-8') as open_file:
            open_file.write(digest)

    return digest


def fixity_copy(source_path, destination_path, store_md5s=True, is_move=False):

    if is_move:
        operation = 'move'
    else:
        operation = 'copy'

    logging.info('Fixity %s %s to %s.', operation, source_path, destination_path)
    # create md5 for source
    md5_1 = generate_file_md5(source_path, store=store_md5s)

    # do the copy
    destination_path = post_move_filename(source_path, destination_path)
    if os.path.exists(destination_path):
        raise IOError(f'Cannot {operation}: Destination {destination_path} already exists.')

    # when there is an error while copying the file, retry it for a set number of times before giving up
    retries = 0
    while True:
        try:
            shutil.copy(source_path, destination_path)
            break
        except OSError as oserr:
            retries += 1
            if retries >= settings.MOVE_RETRIES:
                logging.warning(
                    'Too many (%s) retries, gave up trying to fixity %s %s to %s.',
                    settings.MOVE_RETRIES,
                    operation,
                    source_path,
                    destination_path,
                )
                raise oserr

            logging.warning('Error: %s', oserr)
            logging.warning(
                'OSError while trying to fixity %s %s to %s. Sleeping to retry later...',
                operation,
                source_path,
                destination_path,
            )
            time.sleep(settings.RETRY_WAIT)

    # create md5 for destination
    md5_2 = generate_file_md5(destination_path, store=store_md5s)

    if md5_1 == md5_2:
        logging.info('Fixity %s complete.', operation)
        return destination_path
    raise IOError("MD5 of source and destination files don't match.")


def fixity_move(source_path, destination_path, store_md5s=True, failsafe_folder=None):
    """
    Move a file from source to destination, checking md5s of both match.

    If failsafe_folder is given, the file (and md5) are (non-fixity) moved to that folder, rather than deleted.
    NB that files already in the failsafe will be overwritten by this process.
    """
    dest_path = fixity_copy(source_path, destination_path, store_md5s, is_move=True)

    if dest_path:  # move completed successfully
        if failsafe_folder:
            failsafe_path = post_move_filename(source_path, failsafe_folder)
            # we have to change the copy_function from copy2 (which attempts to copy the file attributes which
            # produces an input/output error. Likely a Docker+Python bug)
            shutil.move(source_path, failsafe_path, copy_function=shutil.copy)
            if store_md5s:
                shutil.move(f'{source_path}.md5', f'{failsafe_path}.md5', copy_function=shutil.copy)
        else:  # delete the original(!)
            os.remove(source_path)
            if store_md5s:
                os.remove(f'{source_path}.md5')

    return dest_path
