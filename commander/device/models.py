"""The ADI-2 families. Each answers SysEx only under its own device ID; the name of its MIDI port is a hint, not
proof, so a connection asks under each ID in turn, the hinted one first.

Commander controls all of an ADI-2 DAC FS. Of an ADI-2 Pro and ADI-2/4 Pro it controls the EQ (bands, Bass/Treble,
presets, Loudness) of Line Out and Phones 3/4. Phones 1/2 shares the signal of Line Out, and has settings of its
own only with Dual Phones on (ADI-2 Pro manual, 8.2): what its addresses do otherwise is not known."""

from collections import namedtuple

from . import MODEL

# id: the device ID in the SysEx header
# name: as shown
# port: part of the name of its MIDI port
# supported: Commander works with it
# outputs: the names of Line Out, Phones 1/2 and Phones 3/4, in the order of params.OUTPUTS
# tags: their marks on a preset that is selected there
# controlled: the output addresses Commander controls
# eq_only: of those Commander controls only the EQ, and none of the device's other settings
# no_bt_from: from this rate on there is no Bass/Treble and no Loudness (manuals, 8.8)
# one_eq_from: from this rate on the EQ runs on one stereo channel only: the input, Line Out or Phones 3/4; None when
#   it never does
# active: per value of the active output in the status message (status.Status.output), the output addresses the
#   device has active. The DAC FS has one at a time. The Pro and ADI-2/4 Pro have Line Out or Phones 1/2, which share
#   a signal, or neither; and Phones 3/4 always
Model = namedtuple("Model", "id name port supported outputs tags controlled eq_only no_bt_from one_eq_from active")

DAC = Model(0x71, MODEL, "ADI-2 DAC", True, ("Line Out", "Phones 1/2", "Phones 3/4 · IEM"), ("L", "P", "I"),
            (3, 6, 9), False, 705600, None, ((3,), (6,), (9,), ()))
PRO = Model(0x72, "ADI-2 Pro", "ADI-2 Pro", True, ("Line Out", "Phones 1/2", "Phones 3/4"), ("L", "P12", "P34"),
            (3, 9), True, 352800, 352800, ((9,), (3, 9), (6, 9), (6, 9)))
PRO_24 = PRO._replace(id=0x73, name="ADI-2/4 Pro", port="ADI-24", one_eq_from=705600)
MODELS = (DAC, PRO, PRO_24)
BY_ID = {m.id: m for m in MODELS}


def probe_order(port_name):
    """All models, the one the port name suggests first."""
    hinted = [m for m in MODELS if m.port in port_name]
    return hinted + [m for m in MODELS if m not in hinted]
