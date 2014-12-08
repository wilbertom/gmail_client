from email.header import decode_header

DEFAULT_CODEC = 'utf-8'

def ensure_encoded(some_str):
    """
    :param some_str:
    :return: Try to encode the string with a series of encodings,
    returning the successfully encoded string. Uses ascii, then utf-8,
    then latin-1. If neither works, force a default.
    """

    try:
        # assume it's bytes, or can be encoded with ascii codec
        return str(some_str)
    except UnicodeEncodeError:
        try:
            return some_str.encode('utf-8')
        except UnicodeEncodeError:
            try:
                return some_str.encode('latin-1')
            except UnicodeEncodeError:
                return some_str.encode(DEFAULT_CODEC, errors='ignore')


def decode_email_header(header):
    # header may come to us as unicode, but `decode_header` expects
    # only bytes or ascii-encodable characters
    encoded_header = ensure_encoded(header)
    # turn RFC-2822-compliant coded bytes into regular encoded bytes
    partially_decoded_header, encoding = \
            decode_header(encoded_header)[0]
    # finally, re-decode using either what `decode_header` tells us
    # to or a default, being lenient just in case we can't handle it
    # for unforeseen reasons
    codec_to_use = encoding or DEFAULT_CODEC
    return partially_decoded_header.decode(codec_to_use, errors='ignore')