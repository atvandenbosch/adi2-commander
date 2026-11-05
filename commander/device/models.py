"""The ADI-2 families. Each answers SysEx only under its own device ID; the name of its MIDI port is a hint, not
proof, so a connection asks under each ID in turn, the hinted one first."""

from collections import namedtuple

from . import MODEL

# id: the device ID in the SysEx header; name: as shown; port: part of the name of its MIDI port;
# supported: Commander works with it
Model = namedtuple("Model", "id name port supported")

DAC = Model(0x71, MODEL, "ADI-2 DAC", True)
PRO = Model(0x72, "ADI-2 Pro", "ADI-2 Pro", False)
PRO_24 = Model(0x73, "ADI-2/4 Pro", "ADI-24", False)
MODELS = (DAC, PRO, PRO_24)
BY_ID = {m.id: m for m in MODELS}


def probe_order(port_name):
    """All models, the one the port name suggests first."""
    hinted = [m for m in MODELS if m.port in port_name]
    return hinted + [m for m in MODELS if m not in hinted]
