"""Copies of the device's state as setup files of ADI-2 Remote, per model: the last KEEP that differ from each other,
named by the model and the time they were taken."""

import datetime
import os

from .conversion import setupfile

KEEP = 5
SUFFIX = ".adistp"


def folder():
    """Where Commander keeps the copies: the user's local application data."""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "ADI-2 Commander", "Backups")


def _prefix(model):
    return model.name.replace("/", "-") + " "


def keep(where, model, text, now=None):
    """Save text as the newest copy of model's state in where, unless the newest copy there holds the same; of the
    model's copies the last KEEP stay. The path written, or None when the newest copy holds the same."""
    os.makedirs(where, exist_ok=True)
    prefix = _prefix(model)
    copies = sorted(f for f in os.listdir(where) if f.startswith(prefix) and f.endswith(SUFFIX))
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
