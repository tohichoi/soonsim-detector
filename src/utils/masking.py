"""Masking for values that must never reach a log in the clear.

A camera URL carries its credentials and gets logged on every reconnect, so the
password would otherwise pile up in plain text on the NAS, in rotated files that
outlive it.
"""

import re

MASK = "<credentials>"
_URL_CREDENTIALS = re.compile(r"(?P<scheme>[A-Za-z][A-Za-z0-9+.\-]*://)[^/\s]+@")


def mask_url_credentials(value: object) -> str:
    """Blank out the user:password part of a URL, keeping host and path readable.

    Greedy up to the last '@' in the authority, so a password that itself
    contains '@' is masked whole rather than only up to the first one.
    """
    return _URL_CREDENTIALS.sub(rf"\g<scheme>{MASK}@", str(value))
