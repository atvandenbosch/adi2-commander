"""Copies of the device's state as setup files of ADI-2 Remote, per device: the last KEEP that differ from each
other, named by the model, the serial number and the time they were taken."""

import datetime
import os
import re

from .conversion import setupfile

KEEP = 5
SUFFIX = ".adistp"


def folder():
    """Where Commander keeps the copies: the user's local application data."""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "ADI-2 Commander", "Backups")


def _prefix(model, serial):
    return model.name.replace("/", "-") + " " + (serial + " " if serial else "")


def keep(where, model, text, now=None, serial=None):
    """Save text as the newest copy of the state of the device, of model with serial number serial (None: unknown),
    in where, unless the newest copy of that device there holds the same; of the device's copies the last KEEP stay.
    The path written, or None when the newest copy holds the same."""
    os.makedirs(where, exist_ok=True)
    prefix = _prefix(model, serial)
    own = re.compile(re.escape(prefix) + r"\d{4}-\d\d-\d\d \d{6}" + re.escape(SUFFIX))
    copies = sorted(f for f in os.listdir(where) if own.fullmatch(f))
    if copies:
        with open(os.path.join(where, copies[-1]), encoding="ascii", errors="replace", newline="") as f:
            if f.read() == text:
                return None
    name = prefix + (now or datetime.datetime.now()).strftime("%Y-%m-%d %H%M%S") + SUFFIX
    path = os.path.join(where, name)
    setupfile.save(path, text)
    for old in sorted(set(copies) | {name})[:-KEEP]:
        os.remove(os.path.join(where, old))
    return path
