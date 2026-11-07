"""The state of a device as a setup file of RME's ADI-2 Remote (.adistp).

The file holds what a dump and the twenty preset slots hold: the input of an ADI-2 Pro or ADI-2/4 Pro with its EQ,
the three outputs with their EQ, the device settings, and the presets with their names. ADI-2 Remote restores it
with File > Open Setup File.... Each output also carries three settings of ADI-2 Remote, with its defaults. Values
are in units (dB, Hz, Q, or an index), with two decimals and a comma. The device settings stand at fixed places,
the same for every model; a place the model has no setting for has no name and 0.
"""

from ..device import models
from ..device import params as P
from .presetfile import BAND_INDICES, BAND_NAMES, BT_NAMES, ROOT, units, val

SLOTS = range(1, 21)
# the settings of an output, in their order: (name, index, increments per unit), and ADI-2 Remote's own
OUTPUT = [("Source", 1, 1), ("AutoRef", 3, 1), ("RefLevel", 2, 1), ("Mono", 4, 1), ("Width", 5, 100),
          ("Polarity", 7, 1), ("MSProcessing", 6, 1), ("Crossfeed", 8, 1), ("DAFilter", 9, 1), ("Deemphasis", 10, 1),
          ("Volume", 12, 10), ("LockVolume", 13, 1), ("Balance", 14, 100), ("Mute", 15, 1), ("Dim", 16, 1),
          ("LoopBack", 17, 1), ("DCProtection", 18, 1), ("RearTRSSource", 19, 1), ("LoudnessEn", 20, 1),
          ("LDBassGain", 21, 2), ("LDTrebleGain", 22, 2), ("LDVolumeRef", 23, 2)]
REMOTE_OWN = [("LinkVolume", 0), ("RecallVolume", -20), ("VolumeLimit", 120)]
# the input, address 0: its settings, and where its Dual EQ is
INPUT = [("AutoRef", 2, 1), ("RefLevel", 1, 1), ("TrimGainLeft", 3, 2), ("TrimGainRight", 4, 2), ("Polarity", 5, 1),
         ("MSProcessing", 6, 1), ("ADFilter", 7, 1), ("ADConversion", 9, 1), ("DCFilter", 10, 1), ("RIAAMode", 11, 1),
         ("RIAAMonoBass", 12, 1), ("BalImpedance", 13, 1)]
INPUT_DUAL_EQ = 8
# the device settings (address 12) by place, their names, and per model the places it has no setting for
DEVICE = [6, 7, 1, 2, 3, 4, 5, 8, 9, 10, 11, 12, 15, 16, 40, 41, 42, 43, 25, 26, 27, 28, 29, 22, 23, 24,
          32, 33, 34, 35, 36, 37, 62]
DEVICE_NAMES = {1: "MuteLineVs", 2: "AutoStandBy", 3: "DSDDetection", 4: "DSDFilter", 5: "DSDDirect", 6: "BasicMode",
                7: "DigitalOutSource", 8: "DualPhones", 9: "BalancedMode", 10: "TogglePhonesLine", 11: "MuteVsPh12",
                12: "MuteVsPh34", 15: "ClockSource", 16: "SampleRate", 25: "RemapKeys", 26: "RemapVol", 27: "RemapIO",
                28: "RemapEQ", 29: "RemapSetup", 22: "RemapIR5", 23: "RemapIR6", 24: "RemapIR7", 40: "SPDIFIn",
                41: "SRCMode", 42: "SRCGain", 43: "OpticalOut", 32: "DisplayMode", 33: "MeterColor", 34: "HorMeter",
                35: "AutoDark", 36: "ShowVolScreen", 37: "LockUI", 62: "LoadVolume"}
PRO_ONLY = {6, 7, 8, 9, 10, 11, 12, 22, 23, 24, 40, 41, 42, 43}
NOT_ON = {models.DAC.id: PRO_ONLY, models.PRO.id: {1}, models.PRO_24.id: {1, 4, 5}}
NAMED = {models.PRO.id: {5: "DSDDirect12"}}
# a preset as the device holds it, besides its bands and Bass/Treble
PRESET_ENABLE = {"Left": 15, "Right": 0}
PRESET_FIXED = [("BassTrebleEn", 0)]
PRESET_TAIL = [("EQ Preset Select", 0), ("Load BT w. EQ", 1)]


def _eq(name, state, left, right, dual):
    """An EQ as the device runs it: the left side with Bass/Treble, the right side."""
    lines = ["\t\t<%s>" % name, val("EQEnable", state[(left, P.EQ_ENABLE)])]
    lines += [val(BAND_NAMES[i], units(i, state[(left, i)])) for i in BAND_INDICES]
    lines += [val(BT_NAMES[i], units(i, state[(left, i)])) for i in sorted(BT_NAMES)]
    lines += [val("DualEQ", dual), val("EQ Preset Select", state[(left, P.EQ_PRESET_SELECT)]),
              val("Load BT w. EQ", state[(left, P.LOAD_BT)]), "\t\t</%s>" % name]
    right_name = name + (" R" if name.startswith("EQOut") else "R")
    lines += ["\t\t<%s>" % right_name, val("EQEnable", state[(right, P.EQ_ENABLE)])]
    lines += [val(BAND_NAMES[i], units(i, state[(right, i)])) for i in BAND_INDICES]
    return lines + ["\t\t</%s>" % right_name]


def _settings(name, state, address, table, own=()):
    lines = ["\t\t<%s>" % name]
    lines += [val(e, state.get((address, i), 0) / scale) for e, i, scale in table]
    lines += [val(e, v) for e, v in own]
    return lines + ["\t\t</%s>" % name]


def _preset(n, slot):
    """A preset slot; an unused one as selecting it loads: the factory bands and Bass/Treble, Dual EQ off."""
    if slot["used"]:
        vals, dual = slot["vals"], slot["dual"]
    else:
        vals = {(a, i): v for a in (13, 14) for i, v in P.FACTORY_BANDS.items()}
        vals.update({(13, i): v for i, v in P.FACTORY_BT.items()})
        dual = 0
    lines = []
    for side, a in (("Left", 13), ("Right", 14)):
        block = "EQPreset%d%s" % (n, side)
        lines += ["\t\t<%s>" % block, val("EQEnable", PRESET_ENABLE[side])]
        lines += [val(BAND_NAMES[i], units(i, vals[(a, i)])) for i in BAND_INDICES]
        if side == "Left":
            lines += [val(e, v) for e, v in PRESET_FIXED]
            lines += [val(BT_NAMES[i], units(i, vals[(a, i)])) for i in sorted(BT_NAMES) if i != P.BT_ENABLE]
            lines += [val("DualEQ", dual)] + [val(e, v) for e, v in PRESET_TAIL]
        lines.append("\t\t</%s>" % block)
    return lines


def write(state, slots, model=models.DAC, revision=None):
    """A device's state (all its addresses, as a dump holds them) and its twenty preset slots ({n: {'used', 'dual',
    'name', 'vals' {(13|14, index): value}}}) as a setup file. revision: the device's, or None when not known, which
    leaves it out. Raises ValueError when the state or the slots are incomplete."""
    if any(n not in slots for n in SLOTS):
        raise ValueError("preset slots not read yet")
    root = ROOT[model.id]
    lines = ["\t<%s>" % root, "\t\t<General>", '\t\t\t<val e="Version" v="2"/>']
    if revision is not None:
        lines.append('\t\t\t<val e="Revision" v="%d"/>' % revision)
    lines.append("\t\t</General>")
    try:
        if model.id != models.DAC.id:
            lines += _settings("Input", state, 0, INPUT)
            lines += _eq("EQInput", state, 1, 2, state[(0, INPUT_DUAL_EQ)])
        for k, (_, out, left, right) in enumerate(P.OUTPUTS, 1):
            lines += _settings("Output%d" % k, state, out, OUTPUT, REMOTE_OWN)
            lines += _eq("EQOut%d" % k, state, left, right, state[(out, P.DUAL_EQ)])
        names = {**DEVICE_NAMES, **NAMED.get(model.id, {})}
        lines.append("\t\t<DevSettings>")
        for i in DEVICE:
            on = i not in NOT_ON[model.id]
            lines.append(val(names[i] if on else "", state.get((12, i), 0) if on else 0))
        lines.append("\t\t</DevSettings>")
        for n in SLOTS:
            lines += _preset(n, slots[n])
    except KeyError as e:
        raise ValueError("state not read yet: %s" % (e.args[0],)) from None
    lines.append("\t\t<PresetNames>")
    lines += ['\t\t\t<val e="EQPresetName%d" v="%s"/>' % (n, slots[n]["name"].strip()) for n in SLOTS]
    return "\n".join(lines + ["\t\t</PresetNames>", "\t</%s>" % root]) + "\n"


def save(path, text):
    with open(path, "w", encoding="ascii", newline="\n") as f:
        f.write(text)
