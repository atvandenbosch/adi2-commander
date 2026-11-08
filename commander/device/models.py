"""The ADI-2 families. Each answers SysEx only under its own device ID; the name of its MIDI port is a hint, not
proof, so a connection asks under each ID in turn, the hinted one first.

Commander controls all of an ADI-2 DAC FS. Of an ADI-2 Pro and ADI-2/4 Pro it controls the EQ (bands, Bass/Treble,
presets, Loudness) of Line Out and Phones 3/4, and of Phones 1/2 while it has settings of its own. Phones 1/2 shares
the signal of Line Out and is active with Dual Phones on; with Mute v. TRS 1/2 on as well it has settings of its own,
otherwise it uses those of Line Out (ADI-2 Pro manual, 14.1.4, 21.4). In Balanced Phones mode it is the right channel
of Phones 3/4 (chapter 18). Commander also controls their Source, as far as the Basic Mode in use allows."""

from collections import namedtuple

from . import MODEL
from . import params as P

# id: the device ID in the SysEx header
# name: as shown
# port: part of the name of its MIDI port
# supported: Commander works with it
# tested: Commander has been tested with an actual device of this model
# outputs: the names of Line Out, Phones 1/2 and Phones 3/4, in the order of params.OUTPUTS
# tags: their marks on a preset that is selected there
# controlled: the output addresses Commander controls
# separate: (output address, (Dual Phones, Mute v. TRS 1/2) indices on address 12): Phones 1/2, which has settings of
#   its own while both are on (Session.phones_1_2)
# eq_only: of those Commander controls only the EQ, and none of the device's other settings
# no_bt_from: from this rate on there is no Bass/Treble and no Loudness (manuals, 8.8)
# one_eq_from: from this rate on the EQ of the input, while it is on, bypasses the EQ of the outputs; None when it
#   never does
# active: per value of the active output in the status message (status.Status.output), the output addresses the
#   device has active. The DAC FS has one at a time. The Pro and ADI-2/4 Pro have Line Out or Phones 1/2, which share
#   a signal, or neither; and Phones 3/4 always
# ref_levels: per output address the names of its Ref Level
# da_filters: per device revision the names of DA Filter
# choices: the names of the other lists on an output address, where they differ from params.CHOICES
# settings: the settings on an output address Commander writes besides the EQ; None for all of them
# sources: the names of Source: of Line Out ("line"), of Phones 3/4 ("phones"; "phones_ex" on an ADI-2/4 Pro EX),
#   and in Basic Mode DAC ("dac"). None for one input of the whole device, params.INPUTS
class Model(namedtuple("Model", "id name port supported tested outputs tags controlled separate eq_only no_bt_from "
                                "one_eq_from active ref_levels da_filters choices settings sources")):
    __slots__ = ()

    def __hash__(self):                          # a model is its device ID
        return hash(self.id)


DAC =Model(0x71, MODEL, "ADI-2 DAC", True, True, ("Line Out", "Phones 1/2", "Phones 3/4 · IEM"), ("L", "P", "I"),
            (3, 6, 9), (), False, 705600, None, ((3,), (6,), (9,), ()),
            ref_levels=P.REF_LEVELS, da_filters=P.DA_FILTERS, choices={}, settings=None, sources=None)

_FILTERS = ["SD Sharp", "SD Slow", "Sharp", "Slow"]
_PHONES = ["Lo-Power", "Hi-Power"]
_INPUTS, _USB = ["Auto", "AES", "SPDIF", "Analog"], ["USB 1/2", "USB 3/4"]
# Loopback to USB: the output's signal to the USB record channels 1/2, 3/4 or 5/6
_LOOPBACK = ["Off"] + [name % ch for ch in ("1/2", "3/4", "5/6")
                       for name in ("pre FX to %s", "post FX to %s", "post %s -6 dB")]
PRO = Model(0x72, "ADI-2 Pro", "ADI-2 Pro", True, False, ("Line Out", "Phones 1/2", "Phones 3/4"),
            ("L", "P12", "P34"), (3, 9), ((6, (8, 11)),), True, 352800, 352800, ((9,), (3, 9), (6, 9), (6, 9)),
            ref_levels={3: ["+4 dBu", "+13 dBu", "+19 dBu", "+24 dBu"], 6: _PHONES, 9: _PHONES},
            da_filters={0: _FILTERS + ["NOS"], **{r: _FILTERS + ["NOS", "SD LD"] for r in (1, 2, 3)}},
            choices={P.LOOPBACK: _LOOPBACK},
            settings=frozenset({P.LOUDNESS_ENABLE, P.LD_BASS, P.LD_TREBLE, P.LD_LOW_VOL_REF, P.SOURCE}),
            sources={"line": _INPUTS[:4], "phones": _INPUTS + _USB,
                     "dac": ["Auto", "AES", "SPDIF coax", "Optical", "Analog"] + _USB})
PRO_24 = PRO._replace(id=0x73, name="ADI-2/4 Pro", port="ADI-24", one_eq_from=705600,
                      sources={**PRO.sources, "phones_ex": _INPUTS + _USB + ["ADAT 3/4"]},
                      ref_levels={3: ["+1 dBu", "+7 dBu", "+13 dBu", "+19 dBu", "+24 dBu"],
                                  6: ["IEM"] + _PHONES, 9: ["IEM"] + _PHONES},
                      da_filters={r: _FILTERS + ["SD LD", "Brickwall", "NOS"] for r in range(4)})
MODELS = (DAC, PRO, PRO_24)
BY_ID = {m.id: m for m in MODELS}


def probe_order(port_name):
    """All models, the one the port name suggests first."""
    hinted = [m for m in MODELS if m.port in port_name]
    return hinted + [m for m in MODELS if m not in hinted]
