# pylint: disable=fixme
# TODO: fix leading zeros bug
def seconds_to_hms(seconds, always_include_hours=False, decimal_places=0, output_frames=False, framerate=24):
    if output_frames:
        decimal_places = 0  # ignore decimal places when using frames
        seconds, secs_decimals = divmod(seconds, 1)
        frames = round(secs_decimals * framerate)
        if frames == framerate:
            seconds += 1
            frames = 0
        f = f':{frames:02d}'
    else:
        f = ''

    if decimal_places == 0:
        # otherwise, 59.6 seconds gets formatted as 00:60
        seconds = round(seconds)

    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)

    total_digits = decimal_places + 2  # 2 leading 0s
    secs_template = f'%0{total_digits}.{decimal_places}f'

    if h or always_include_hours:
        return ('%02d:%02d:' + secs_template + '%s') % (h, m, s, f)
    return ('%02d:' + secs_template + '%s') % (m, s, f)


def hms_to_seconds(hms_str):
    sections = hms_str.split(':')
    if len(sections) == 4:
        h, m, s, f = sections
    elif len(sections) == 3:
        h, m, s = hms_str.split(':')
        f = 0  # frames
    else:
        raise ValueError('Expected 3 or 4 segments in the time code')

    return int(h) * 3600 + int(m) * 60 + int(s) + (int(f) / 25.0)
