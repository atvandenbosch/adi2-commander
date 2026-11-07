"""EQ settings as a preset file of RME's ADI-2 Remote (.adieqpr). No Qt.

The file holds one preset: the left EQ with Bass/Treble, the right EQ, and the name. ADI-2 Remote opens it in its
EQ Preset Editor (File > Load) into the preset slot selected there, which Store then writes to the device. Values
are in units (dB, Hz, Q, or an index), with two decimals and a comma; the slot number in the block names does not
choose the slot. The root element names the model, General its device revision.
"""

from ..device import models
from ..device import params as P

ROOT = {models.DAC.id: "ADI-2DAC", models.PRO.id: "ADI-2PRO", models.PRO_24.id: "ADI-24PROSE"}
SLOT = 1
# EQEnable of a preset, left and right, as ADI-2 Remote writes it
ENABLE = {"Left": 15, "Right": 0}
BAND_NAMES = {i: "EQBand%d%s" % (band, part) for band, indices in P.BANDS.items()
              for part, i in zip(("Type", "Gain", "Freq", "Q"), indices) if i is not None}
BT_NAMES = {P.BT_ENABLE: "BassTrebleEn", P.BASS[0]: "EQBassGain", P.BASS[1]: "EQBassFreq", P.BASS[2]: "EQBassQ",
            P.TREBLE[0]: "EQTrebleGain", P.TREBLE[1]: "EQTrebleFreq", P.TREBLE[2]: "EQTrebleQ"}
BAND_INDICES = sorted(BAND_NAMES)


def name_of(text):
    """A preset name from text: the signs the device takes, up to their number."""
    return "".join(c for c in text if c in P.NAME_SIGNS)[:P.NAME_LENGTH].strip()


def _value(index, raw):
    if index in P.GAIN_INDICES:
        return raw / 2
    if index in P.Q_INDICES:
        return raw / 10
    return raw


def _val(name, value):
    return '\t\t\t<val e="%s" v="%.2f,"/>' % (name, value)


def write(state, out, name, model=models.DAC, revision=None):
    """The EQ of output out (or of the preset being edited, held at its addresses) as a preset file named name.
    revision: the device's, or None when not known, which leaves it out. Raises ValueError when the state of the
    output is incomplete."""
    _, out, left, right = next(o for o in P.OUTPUTS if o[1] == out)
    keys = [(left, i) for i in BAND_INDICES + sorted(BT_NAMES) + [P.LOAD_BT]] + [(right, i) for i in BAND_INDICES]
    if any(k not in state for k in keys + [(out, P.DUAL_EQ)]):
        raise ValueError("EQ of %s not read yet" % model.outputs[P.OUTPUT_ADDRESSES.index(out)])
    root = ROOT[model.id]
    lines = ["\t<%s>" % root, "\t\t<General>", '\t\t\t<val e="Version" v="2"/>']
    if revision is not None:
        lines.append('\t\t\t<val e="Revision" v="%d"/>' % revision)
    lines.append("\t\t</General>")
    for side, addr in (("Left", left), ("Right", right)):
        block = "EQPreset%d%s" % (SLOT, side)
        lines += ["\t\t<%s>" % block, _val("EQEnable", ENABLE[side])]
        lines += [_val(BAND_NAMES[i], _value(i, state[(addr, i)])) for i in BAND_INDICES]
        if side == "Left":
            lines += [_val(BT_NAMES[i], _value(i, state[(addr, i)])) for i in sorted(BT_NAMES)]
            lines += [_val("DualEQ", state[(out, P.DUAL_EQ)]), _val("EQ Preset Select", 0),
                      _val("Load BT w. EQ", state[(addr, P.LOAD_BT)])]
        lines.append("\t\t</%s>" % block)
    lines += ["\t\t<PresetNames>", '\t\t\t<val e="EQPresetName%d" v="%s"/>' % (SLOT, name), "\t\t</PresetNames>",
              "\t</%s>" % root]
    return "\n".join(lines) + "\n"


def save(path, text):
    with open(path, "w", encoding="ascii", newline="\n") as f:
        f.write(text)
