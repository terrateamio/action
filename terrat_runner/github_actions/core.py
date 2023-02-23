import json
import sys


ESCAPED_DATA = [
    ('%', '%25'),
    ('\r', '%0D'),
    ('\n', '%0A'),
]

ESCAPED_PROPERTY = [
    ('%', '%25'),
    ('\r', '%0D'),
    ('\n', '%0A'),
    (':', '%3A'),
    (',', '%2C')
]

CMD_STR = '::'


def _to_cmd_value(v):
    if v is None:
        return ''
    elif isinstance(v, str):
        return v
    else:
        return json.dumps(v)


def _escape_data(v):
    s = _to_cmd_value(v)
    for search, replace in ESCAPED_DATA:
        s = s.replace(search, replace)
    return s


def _escape_property(v):
    s = _to_cmd_value(v)
    for search, replace in ESCAPED_PROPERTY:
        s = s.replace(search, replace)
    return s


def _encode_properties(properties):
    if properties:
        return ' ' + ','.join(['{}={}'.format(k, _escape_property) for k, v in properties.items()])
    else:
        return ''


def issue_cmd(cmd, properties, msg):
    s = CMD_STR + cmd + _encode_properties(properties) + CMD_STR + _escape_data(msg)
    return sys.stdout.write(s + '\n')


def set_secret(secret):
    return issue_cmd('add-mask', {}, secret)
