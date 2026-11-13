"""The ADI-2 families. Each answers SysEx only under its own device ID; the name of its MIDI port is a hint, not
proof, so a connection asks under each ID in turn, the hinted one first.

Commander controls all of an ADI-2 DAC FS. Of an ADI-2 Pro and ADI-2/4 Pro it controls the EQ (bands, Bass/Treble,
presets, Loudness) and the other settings of Line Out and Phones 3/4, and of Phones 1/2 while it has settings of its
own. Phones 1/2 shares
the signal of Line Out and is active with Dual Phones on; with Mute v. TRS 1/2 on as well it has settings of its own,
otherwise it uses those of Line Out (ADI-2 Pro manual, 14.1.4, 21.4). In Balanced Phones mode it is the right channel
of Phones 3/4 (chapter 18). Commander also controls their Source, as far as the Basic Mode in use allows, the
settings of their analog input, and the settings of the device."""

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
# borrowed: per address the settings that are another output's, at that output's address: {address: (that output's
#   address, indices)}. Phones 1/2 of the ADI-2 Pro uses these of Line Out, as it shares Line Out's D/A converter
# no_bt_from: from this rate on there is no Bass/Treble and no Loudness (manuals, 8.8)
# one_eq_from: from this rate on the EQ of the input, while it is on, bypasses the EQ of the outputs; None when it
#   never does
# active: per value of the active output in the status message (status.Status.output), the output addresses the
#   device has active. The DAC FS has one at a time. The Pro and ADI-2/4 Pro have Line Out or Phones 1/2, which share
#   a signal, or neither; and Phones 3/4 always
# ref_levels: per output address the names of its Ref Level
# ref_dbu: per output address each value of its Ref Level as a level in dBu
# shared_ref_level: of Phones 1/2 that uses the settings of Line Out, the names of its Ref Level per value of Line
#   Out's, which sets it; None where Phones 1/2 keeps a Ref Level of its own
# da_filters: per device revision the names of DA Filter
# choices: the names of the other lists on an output address, where they differ from params.CHOICES
# input: the settings of the analog input that differ per model (params.INPUT_CHOICES has the others), per index its
#   params.Choices; None for a model without an analog input. input_ex: on an ADI-2/4 Pro EX (revision 1 and up), what
#   it has instead or besides
# ad_filter_fixed_from: from this rate on the analog input uses one AD Filter, Slow, whatever is chosen
# sources: the names of Source: of Line Out ("line"), of Phones 3/4 ("phones"; "phones_ex" on an ADI-2/4 Pro EX),
#   and in Basic Mode DAC ("dac"). None for one input of the whole device, params.INPUTS
# rumble: it has Rumble, a preset built in behind Clear (params.RUMBLE)
# device: the settings of the device that can be set (params.DEVICE_ADDRESS), grouped and named as on its front panel,
#   a group for each subject of a page: (group, (params.Setting, ...)) each. A device has those it reports. A key
#   (params.KEYS) has the names of keys
# clock: Clock Source, a params.Setting, where it can be chosen; None where the device follows Source
# keys: the functions its keys can have, a params.Keys
class Model(namedtuple("Model", "id name port supported tested outputs tags controlled separate borrowed no_bt_from "
                                "one_eq_from active ref_levels ref_dbu shared_ref_level da_filters choices input "
                                "input_ex ad_filter_fixed_from sources rumble device clock keys")):
    __slots__ = ()

    def __hash__(self):                          # a model is its device ID
        return hash(self.id)


_S = P.Setting
_POWER = ("POWER", (_S(P.AUTO_STANDBY, "Auto Standby", ["Off", "30 min", "1 h", "2 h", "4 h"]),))
_DETECTION = _S(P.DSD_DETECTION, "DSD Detection", None)
_DISPLAY = ("DISPLAY", (_S(P.DISPLAY_MODE, "Display Mode", ["Default", "Dark"]),
                        _S(P.METER_COLOR, "Meter Color", ["Green", "Cyan", "Amber", "Monochrome", "Red", "Orange"]),
                        _S(P.HOR_METER, "Hor. Meter", ["Post FX", "Pre FX", "Dual", "Post FX dBu"]),
                        _S(P.AUTODARK, "AutoDark Mode", None), _S(P.VOLUME_SCREEN, "Show Vol. Screen", None),
                        _S(P.LOCK_UI, "Lock UI", ["Off", "Remote", "Keys", "Keys+Remote"])))
_SETUPS = ["Setup %d" % n for n in range(1, 10)]
_EQ_PRESETS = ["EQ Preset %d" % n for n in range(1, 10)]
_CROSSFEEDS = ["Crossfeed %d" % n for n in range(1, 6)]


def _keys(names, groups, revised=None, dac_mode=()):
    """A params.Keys whose groups and dac_mode name their values, or give a value whose name is revised."""
    at = {name: v for v, name in enumerate(names) if name is not None}
    value = lambda x: None if x is None else at.get(x, x)                      # noqa: E731
    return P.Keys(names, tuple((g, tuple(map(value, xs))) for g, xs in groups), revised or {},
                  frozenset(map(value, dac_mode)))


def _keys_group(keys, settings):
    """The group KEYS: Remap Keys, then each key (params.KEYS) of settings, (index, name) each, with the names of
    keys."""
    return ("KEYS", (_S(P.REMAP_KEYS, "Remap Keys", ["Off", "On", "Remote"]),)
            + tuple(_S(i, name, keys.names) for i, name in settings))


_DAC_FILTER_KEY = 32                             # DA SD LD on an AK4493, DA Brickwall on an ES9028Q2M
_DAC_KEYS = _keys(["Default"] + _SETUPS
                  + ["Mono", "Mono to L", "Mute", "Loudness", "EQ enable", "B/T enable", "EQ+B/T+Ld", "Toggle Ph/Line",
                     "Polarity", "AutoDark", "Dim", "Toggle View"] + _CROSSFEEDS
                  + ["DA SD Sharp", "DA SD Slow", "DA Sharp", "DA Slow", "DA NOS", None] + _EQ_PRESETS,
                  (("Output", ("Mono", "Mono to L", "Mute", "Loudness", "EQ enable", "B/T enable", "EQ+B/T+Ld",
                               None, "Dim", "Polarity", "Toggle Ph/Line")),
                   ("Crossfeed", _CROSSFEEDS),
                   ("DA Filter", ("DA SD Sharp", "DA SD Slow", "DA Sharp", "DA Slow", "DA NOS", _DAC_FILTER_KEY)),
                   ("Setup", _SETUPS), ("EQ Preset", _EQ_PRESETS), ("Display", ("Toggle View", "AutoDark"))),
                  revised={_DAC_FILTER_KEY: {1: "DA SD LD", 2: "DA Brickwall"}})
_DAC_KEY_SETTINGS = ((26, "VOL (1)"), (27, "I/O (2)"), (28, "EQ (3)"), (29, "SETUP (4)"))
DAC =Model(0x71, MODEL, "ADI-2 DAC", True, True, ("Line Out", "Phones 1/2", "Phones 3/4 · IEM"), ("L", "P", "I"),
            (3, 6, 9), (), {}, 705600, None, ((3,), (6,), (9,), ()),
            ref_levels=P.REF_LEVELS, ref_dbu=P.REF_DBU, shared_ref_level=None, da_filters=P.DA_FILTERS,
            choices={}, input=None, input_ex={}, ad_filter_fixed_from=None, sources=None, rumble=False,
            device=(("PHONES", (_S(P.MUTE_LINE, "Mute Line", ["Off", "vs. Phones", "Toggle Ph/Line",
                                                              "Toggle Plugged"]),)),
                    ("DSD", (_S(P.DSD_DIRECT, "DSD Direct (Line)", None),
                             _S(P.DSD_FILTER, "DSD Filter", ["50 kHz", "70 kHz"]), _DETECTION)),
                    _POWER, _DISPLAY, _keys_group(_DAC_KEYS, _DAC_KEY_SETTINGS)),
            clock=None, keys=_DAC_KEYS)

_FILTERS = ["SD Sharp", "SD Slow", "Sharp", "Slow"]
_PHONES = ["Lo-Power", "Hi-Power"]
_INPUTS, _USB = ["Auto", "AES", "SPDIF", "Analog"], ["USB 1/2", "USB 3/4"]
# Loopback to USB: the output's signal to the USB record channels 1/2, 3/4 or 5/6
_LOOPBACK = ["Off"] + [name % ch for ch in ("1/2", "3/4", "5/6")
                       for name in ("pre FX to %s", "post FX to %s", "post %s -6 dB")]
_RIAA = ["+14 dB", "+20 dB", "+26 dB", "+32 dB", "+38 dB"]      # RIAA Mode: the gains
_AUTO = ["Off", "On", "Auto"]
_PRO_MODE = ("DEVICE MODE", (_S(P.BASIC_MODE[1], "Basic Mode", P.BASIC_MODES),
                             _S(P.DIG_OUT_SOURCE, "Dig. Out Source", ["Default", "Main Out"])))
_TOGGLE = _S(P.TOGGLE_PH_LINE, "Toggle Ph/Line", ["Off", "1/2", "3/4", "1/2+3/4", "All Plugged", "Line/Digital"])
_SPDIF = ("SPDIF", (_S(P.SPDIF_IN, "SPDIF In", ["Auto", "Coax", "Optical"]),
                      _S(P.SRC, "SRC", ["Off", "AES In", "SPDIF In"]),
                      _S(P.SRC_GAIN, "SRC Gain dig.", ["0 dB", "-3 dB"]),
                      _S(P.OPTICAL_OUT, "Optical Out", ["SPDIF", "ADAT"])))
_PRO_KEYS_FROM = (["Default"] + _SETUPS
                  + ["Mono 1/2", "Mono 3/4", "Mono 1/2 to L", "Mono 3/4 to L", "Mute 1/2", "Mute 3/4", "Mute all",
                     "Loudness 1/2", "Loudness 3/4", "EQ In 1/2", "EQ Out 1/2", "EQ Out 3/4", "B/T Out 1/2",
                     "B/T Out 3/4", "EQ+B/T+Ld 1/2", "EQ+B/T+Ld 3/4", "Toggle Ph/Line", "EQ+B/T+Ld 1-4", "Polarity"]
                  + _CROSSFEEDS + ["DA SD Sharp", "DA SD Slow", "DA Sharp", "DA Slow"])        # 0 .. 37
_PRO_OUTPUTS = ("Mono 1/2", "Mono 3/4", "Mono all", None, "Mono 1/2 to L", "Mono 3/4 to L", "Mono all to L", None,
                "Mute 1/2", "Mute 3/4", "Mute all", None, "Loudness 1/2", "Loudness 3/4", "Loudness all", None,
                "EQ Out 1/2", "EQ Out 3/4", "EQ Out all", None, "B/T Out 1/2", "B/T Out 3/4", "BT all", None,
                "EQ+B/T+Ld 1/2", "EQ+B/T+Ld 3/4", "EQ+B/T+Ld 1-4", None, "DIM", "Polarity", "Toggle Ph/Line",
                "EQ In 1/2")
_PRO_SOURCES = ("Source AES", "Source SPDIF coax", "Source Optical", "Source Analog", "Source USB 1/2")
_PRO_KEYS_TO = ["Toggle View", "DIM", "Mono all", "Mono all to L", "Loudness all", "EQ Out all", "BT all",
                *_PRO_SOURCES, "AutoDark"] + _EQ_PRESETS
_RIAA_KEYS = ("RIAA Mode +", "RIAA Mode -", "RIAA Mono B.")


def _pro_keys(filters, riaa=()):
    """The functions of the keys of an ADI-2 Pro or ADI-2/4 Pro, with its DA Filter functions 38 and up."""
    return _keys(_PRO_KEYS_FROM + filters + _PRO_KEYS_TO + list(riaa),
                 (("Outputs", _PRO_OUTPUTS), ("Crossfeed", _CROSSFEEDS),
                  ("DA Filter", ("DA SD Sharp", "DA SD Slow", "DA Sharp", "DA Slow", *filters)),
                  ("Source", _PRO_SOURCES)) + ((("RIAA", riaa),) if riaa else ())
                 + (("Setup", _SETUPS), ("EQ Preset", _EQ_PRESETS), ("Display", ("Toggle View", "AutoDark"))),
                 dac_mode=_PRO_SOURCES)


_PRO_KEY_SETTINGS = _DAC_KEY_SETTINGS + ((22, "IR 5"), (23, "IR 6"), (24, "IR 7"))
_PRO_KEYS = _pro_keys(["DA NOS", "DA SD LD"])
_PRO_24_KEYS = _pro_keys(["DA SD LD", "DA Brickwall", "DA NOS"], _RIAA_KEYS)
# Phones 1/2 of the ADI-2 Pro: Line Out's Source, Mono, Width, DA Filter, De-Emphasis, Lock Volume, Mute, Dim,
# Loopback, Dig. DC Protection and Load B/T
_BORROWED = {6: (3, (P.SOURCE, P.MONO, P.WIDTH, P.DA_FILTER, P.DE_EMPHASIS, P.LOCK_VOLUME, P.MUTE, P.DIM, P.LOOPBACK,
                     P.DC_PROTECTION)), 7: (4, (P.LOAD_BT,))}
PRO = Model(0x72, "ADI-2 Pro", "ADI-2 Pro", True, False, ("Line Out", "Phones 1/2", "Phones 3/4"),
            ("L", "P12", "P34"), (3, 9), ((6, (8, 11)),), _BORROWED, 352800, 352800,
            ((9,), (3, 9), (6, 9), (6, 9)),
            ref_levels={3: ["+4 dBu", "+13 dBu", "+19 dBu", "+24 dBu"], 6: _PHONES, 9: _PHONES},
            ref_dbu={3: (4, 13, 19, 24), 6: (7, 22), 9: (7, 22)},
            shared_ref_level=["+7 dBu", "+16 dBu", "+22 dBu", "+22 dBu"],      # 3 dB higher, +22 dBu at most
            da_filters={0: _FILTERS + ["NOS"], **{r: _FILTERS + ["NOS", "SD LD"] for r in (1, 2, 3)}},
            choices={P.LOOPBACK: _LOOPBACK},
            input={P.IN_REF_LEVEL: P.Choices(["+4 dBu", "+13 dBu", "+19 dBu", "+24 dBu"]),
                   P.DC_FILTER: P.Choices(["Auto", "ADC", "RME", "None"])},
            input_ex={}, ad_filter_fixed_from=352800,
            sources={"line": _INPUTS[:4], "phones": _INPUTS + _USB,
                     "dac": ["Auto", "AES", "SPDIF coax", "Optical", "Analog"] + _USB}, rumble=False,
            device=(_PRO_MODE,
                    ("PHONES", (_S(P.DUAL_PHONES, "Dual Phones", None), _S(P.BAL_PHONES, "Bal Phones Mode", _AUTO),
                                _TOGGLE, _S(P.MUTE_V_PH_1_2, "Mute v. TRS 1/2", None),
                                _S(P.MUTE_V_PH_3_4, "Mute v. TRS 3/4", None))),
                    ("DSD", (_S(P.DSD_DIRECT, "DSD Direct 1/2", None),
                             _S(P.DSD_FILTER, "DSD Filter", ["50 kHz", "150 kHz"]), _DETECTION)),
                    _SPDIF, _POWER, _DISPLAY, _keys_group(_PRO_KEYS, _PRO_KEY_SETTINGS)),
            clock=_S(P.CLOCK_SOURCE, "Clock Source", ["Auto", "INT", "AES", "SPDIF"]), keys=_PRO_KEYS)
PRO_24 = PRO._replace(id=0x73, name="ADI-2/4 Pro", port="ADI-24", borrowed={}, one_eq_from=705600,
                      sources={**PRO.sources, "phones_ex": _INPUTS + _USB + ["ADAT 3/4"]},
                      ref_levels={3: ["+1 dBu", "+7 dBu", "+13 dBu", "+19 dBu", "+24 dBu"],
                                  6: ["IEM"] + _PHONES, 9: ["IEM"] + _PHONES},
                      ref_dbu={3: (1, 7, 13, 19, 24), 6: (1, 7, 19), 9: (1, 7, 19)}, shared_ref_level=None,
                      da_filters={r: _FILTERS + ["SD LD", "Brickwall", "NOS"] for r in range(4)},
                      input={P.IN_REF_LEVEL: P.Choices(["+1 dBu", "+7 dBu", "+13 dBu", "+19 dBu", "+24 dBu"]),
                             P.DC_FILTER: P.Choices(["RME", "None"]), P.RIAA_MODE: P.Choices(["Off"] + _RIAA),
                             P.RIAA_MONO_BASS: P.Choices(["Off", "Mono"])},
                      input_ex={P.IN_REF_LEVEL: P.Choices(["%d dBu (dig.)" % dbu for dbu in range(-35, 0, 6)]
                                                          + ["+1 dBu", "+7 dBu", "+13 dBu", "+19 dBu", "+24 dBu"], -6),
                                P.DC_FILTER: P.Choices(["ADC", "RME", "None"]),
                                P.RIAA_MODE: P.Choices(["Off", "0 dB"] + _RIAA),
                                P.BAL_IMPEDANCE: P.Choices(["94 kΩ", "47 kΩ"])},
                      ad_filter_fixed_from=705600, rumble=True,
                      device=(_PRO_MODE,
                              ("PHONES", (_S(P.DUAL_PHONES, "Dual Phones", None),
                                          _S(P.BAL_PHONES, "Bal TRS Mode", _AUTO), _TOGGLE,
                                          _S(P.MUTE_V_PH_1_2, "Mute v. Ph 1/2", None),
                                          _S(P.MUTE_V_PH_3_4, "Mute v. Ph 3/4", None))),
                              ("DSD", (_DETECTION,)), _SPDIF, _POWER, _DISPLAY,
                              _keys_group(_PRO_24_KEYS, _PRO_KEY_SETTINGS)),
                      keys=_PRO_24_KEYS)
MODELS = (DAC, PRO, PRO_24)
BY_ID = {m.id: m for m in MODELS}


def channel_name(model, out):
    """The name of the output at address out as model has it, or of the analog input."""
    return P.channel(out)[0] if out == P.INPUT_ADDRESS else model.outputs[P.OUTPUT_ADDRESSES.index(out)]


def full_name(model, revision):
    """The name of the model; of an ADI-2/4 Pro with SE (revision 0) or EX (1 and up) once the revision is known."""
    if model.id != PRO_24.id or revision is None:
        return model.name
    return model.name + (" EX" if revision >= 1 else " SE")


def probe_order(port_name):
    """All models, the one the port name suggests first."""
    hinted = [m for m in MODELS if m.port in port_name]
    return hinted + [m for m in MODELS if m not in hinted]
