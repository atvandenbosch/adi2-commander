"""The settings of the device itself, named as on its front panel: those of the model (Model.device), as far as the
device reports them (Session.device_settings). On two pages: Audio, what the signal goes through, and Controls, the
power, the display and the keys of the device. The page chosen stays while Commander runs.

    one of a few values     a stepper (‹ value ›)
    on or off               an option
    the function of a key   a field with a menu of the functions in groups (value ▾)

Mute v. Ph 1/2 can be set with Dual Phones on only, SPDIF In outside Basic Mode DAC, where Source chooses the SPDIF
input. DSD Filter, on a device with DSD Direct, is faded while DSD Direct is off; the keys while Remap Keys is off,
and a key whose function takes effect in Basic Mode DAC only, outside it. The clock is in the input panel. Under the
keys, Factory Settings sets Remap Keys and the keys as from the factory (Keys.factory).
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ..device import models
from ..device import params as P
from .inputs import NOT_IN_DAC_MODE
from .output import LABEL_WIDTH, NAME_INDENT, VALUE_WIDTH, _label, _row
from .widgets import (ATTACHED_GAP, GROUP_STYLE, INNER_GAP, TITLE_STYLE, Action, GroupedChoice, Option, Segmented,
                      Stepper, head)

# what each setting chooses; below it, briefly, a value whose name does not say it all
TIPS = {
    P.MUTE_LINE: "When Line Out is muted for Phones and IEM\n"
                 "vs. Phones: with a plug in; Toggle: by pushing VOLUME for half a second\n"
                 "Toggle Plugged: also between Phones and IEM, those with a plug in",
    P.AUTO_STANDBY: "After how long without a signal or use the device goes to standby\n"
                    "The connection to Commander does not keep it on.",
    P.DSD_DETECTION: "Whether the device recognises DSD (DoP) on %(inputs)s",
    P.DSD_DIRECT: "Whether DSD goes to Line Out directly, past all processing and Volume\n"
                  "On: Ref Level sets its level; %(phones)s off.",
    P.DSD_FILTER: "Where the noise filter for DSD cuts off\n50 kHz suits DSD64, %(high)s DSD128 and up.",
    P.BASIC_MODE[1]: "What the device works as: which inputs go to which outputs\n"
                     "Auto: by what is connected; INPUT shows the mode in use.",
    P.DIG_OUT_SOURCE: "What the digital outputs carry\nMain Out: the signal of Line Out, with EQ and Volume",
    P.DUAL_PHONES: "Whether Phones 1/2 is active beside Phones 3/4",
    P.BAL_PHONES: "Whether Phones 3/4 and Phones 1/2 form one balanced output\nAuto: while both have a plug in",
    P.TOGGLE_PH_LINE: "Which outputs Line Out swaps with when VOLUME is pushed for half a second\n"
                      "All Plugged: the phones with a plug in; Line/Digital: the digital outputs",
    P.MUTE_V_PH_1_2: "Whether a plug in Phones 1/2 mutes Line Out\nOn: Phones 1/2 also has settings of its own.",
    P.MUTE_V_PH_3_4: "Whether a plug in Phones 3/4 mutes Line Out",
    P.SPDIF_IN: "Which SPDIF input the device takes",
    P.SRC: "Which input the sample rate converter brings to the device's clock\nOff for DSD (DoP)",
    P.SRC_GAIN: "The level after the sample rate converter, for USB recording and Dig Thru\n"
                "-3 dB: room for peaks up to +3 dBFS",
    P.OPTICAL_OUT: "What the optical output sends\nIn Dig Thru: ADAT when ADAT comes in",
    P.DISPLAY_MODE: "The colours of the device's menus\nDark: light text on black",
    P.METER_COLOR: "The colour of the level meters on the device's display",
    P.HOR_METER: "What the horizontal level meter on the device's display shows\n"
                 "Post FX: after the processing and Volume; Pre FX: before it; Dual: both",
    P.AUTODARK: "Whether the display and the LEDs go dark after 10 seconds without use",
    P.VOLUME_SCREEN: "Whether turning VOLUME shows the Volume screen",
    P.LOCK_UI: "What on the device is locked; VOLUME always works.\n"
               "To unlock on the device, hold encoder 1. Commander can still change it.",
    P.REMAP_KEYS: "Which keys have the functions chosen below\n"
                  "Remote: keys %(remote_keys)s on the remote control\n"
                  "On: also VOL, I/O, EQ and SETUP on the device; held for half a second, they open their menu.\n"
                  "Off: none; keys %(remote_keys)s on the remote control do nothing.",
}
# a key's tooltip by Remap Keys (Off, On, Remote) and by whether it has a function (value 0, Default, has none):
# %(device)s is its key on the device, %(n)d its key on the remote control
KEY_TIPS = {
    (1, True): "The function of %(device)s on the device and of key %(n)d on the remote control; "
               "held for half a second, %(device)s opens its menu.",
    (1, False): "No function: %(device)s on the device opens its menu and key %(n)d on the remote control does "
                "nothing.",
    (2, True): "Remap Keys is Remote, so this is the function of key %(n)d on the remote control; %(device)s on the "
               "device opens its menu.",
    (2, False): "Remap Keys is Remote, so key %(n)d on the remote control does nothing; %(device)s on the device "
                "opens its menu.",
    (0, None): "Remap Keys is off, so %(device)s on the device opens its menu and key %(n)d on the remote control "
               "does nothing.",
}
# a key on the remote control only (IR 5 .. IR 7)
REMOTE_KEY_TIPS = {True: "The function of key %(n)d on the remote control",
                   False: "No function: key %(n)d on the remote control does nothing.",
                   None: "Remap Keys is off, so key %(n)d on the remote control does nothing."}
# the keys on the device whose names a fixed key on the remote control has too
SAME_NAME = "Note: the %s key on the remote control is a separate key, not affected by Remap Keys."
# a button under the keys: Remap Keys and every key as from the factory
FACTORY = "Factory Settings"
FACTORY_TIP = "Sets Remap Keys and the keys as from the factory:\n%s"
AT_FACTORY = "Sets Remap Keys and the keys as from the factory.\nThey are already set this way."
EXTRA = {(models.PRO.id, P.BAL_PHONES): "Line Out is then muted.",
         (models.PRO_24.id, P.BAL_PHONES): "The Pentaconn jack is always balanced."}
NEEDS_DUAL_PHONES = "Can be set with Dual Phones on"
PAGES = ("Audio", "Controls")
CONTROLS = {"POWER", "DISPLAY", "KEYS"}          # the groups on the second page
NOT_IN_USE = "Not in use: DSD Direct is off."
DAC_MODE_ONLY = "Takes effect in Basic Mode DAC"


def tip(model, setting):
    """What setting chooses, on model."""
    pro = model.sources is not None                   # an ADI-2 Pro or ADI-2/4 Pro
    text = TIPS[setting.index] % {"inputs": "AES, SPDIF and USB" if pro else "SPDIF and USB",
                                  "phones": "Phones 1/2 is" if pro else "Phones and IEM are",
                                  "high": setting.names[1] if setting.names else "",
                                  "remote_keys": "1–7" if pro else "1–4"}
    extra = EXTRA.get((model.id, setting.index))
    return text if extra is None else text + "\n" + extra


def key_tip(setting, remap, value):
    """What a key does with Remap Keys at remap (None: not known yet, taken as On) and its function value."""
    n, device = P.KEYS.index(setting.index) + 1, setting.name.split()[0]
    remap = 1 if remap is None else remap
    has = None if remap == 0 else value != 0
    if n > 4:
        return REMOTE_KEY_TIPS[has] % {"n": n}
    text = KEY_TIPS[remap, has] % {"n": n, "device": device}
    return text + "\n" + SAME_NAME % device if device in ("VOL", "EQ") else text


class DevicePanel(QWidget):
    edited = Signal(object, int, bool)               # key, value, rounded or clamped: as the output panel's

    def __init__(self, session, marks):
        super().__init__()
        self.session, self.marks, self.model = session, marks, None
        self.built = None                                # the groups and settings the rows are for
        self.steppers, self.options = {}, {}
        self.factory = None                              # the button under the keys, with the group KEYS
        self.page, self.pages = 0, []                    # the page shown; the widget of each
        title = QLabel("DEVICE")
        title.setStyleSheet(TITLE_STYLE)
        self.choice = Segmented(PAGES)
        self.choice.changed.connect(self.show_page)
        self.choice.setFixedWidth(LABEL_WIDTH + VALUE_WIDTH)                  # as wide as the rows
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(0)
        self.lay.addWidget(head(title))
        self.lay.addSpacing(ATTACHED_GAP)
        self.lay.addWidget(self.choice)
        self.body = QWidget()
        self.lay.addWidget(self.body)
        self.lay.addStretch()

    def set_model(self, model):
        """All settings of model, until a device of it reports its own."""
        self.model = model
        self.build(model.device)

    def build(self, groups):
        groups = tuple((g, tuple(xs)) for g, xs in groups)
        if groups == self.built:
            return
        self.built = groups
        self.steppers, self.options, self.factory = {}, {}, None
        body = QWidget()
        outer = QVBoxLayout(body)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.pages, pages = [], []
        for _ in PAGES:
            page = QWidget()
            pages.append(QVBoxLayout(page))
            pages[-1].setContentsMargins(0, 0, 0, 0)
            pages[-1].setSpacing(0)
            outer.addWidget(page)
            self.pages.append(page)
        for g, xs in groups:
            lay = pages[g in CONTROLS]
            lay.addSpacing(INNER_GAP)
            group = QLabel(g)
            group.setStyleSheet(GROUP_STYLE)
            lay.addWidget(head(group))
            lay.addSpacing(ATTACHED_GAP)
            for x in xs:
                lay.addWidget(self._control(x))
            if g == "KEYS":
                self.factory = Action(compact=True)
                self.factory.setText(FACTORY)
                self.factory.clicked.connect(self.to_factory)
                lay.addWidget(_row(_label(""), self.factory))
        self.lay.replaceWidget(self.body, body)
        self.body.setParent(None)
        self.body.deleteLater()
        self.body = body
        self.show_page(self.page)

    def show_page(self, i):
        self.page = i
        self.choice.set_current(i)
        for n, page in enumerate(self.pages):
            page.setVisible(n == i)

    def _control(self, x):
        """The row of one setting: its name, then what sets it; an option carries its own name."""
        if x.names is None:
            option = Option(x.name)
            option.clicked.connect(lambda i=x.index: self.toggle(i))
            self.options[x.index] = (x, option)
            return _row(option, indent=NAME_INDENT - Option.RING - 1)        # the track where the names start
        if x.index in P.KEYS:
            keys = self.model.keys
            s = GroupedChoice(x.names, keys.groups, tips=dict.fromkeys(keys.dac_mode, DAC_MODE_ONLY))
        else:
            s = Stepper(x.names, off=x.names.index("Off") if "Off" in x.names else None)
        s.setFixedWidth(VALUE_WIDTH)
        s.chosen.connect(lambda value, i=x.index: self.edited.emit((P.DEVICE_ADDRESS, i), value, False))
        self.steppers[x.index] = (x, s)
        return _row(_label(x.name), s)

    def toggle(self, i):
        key = (P.DEVICE_ADDRESS, i)
        if self.session.writable(key):
            self.edited.emit(key, 1 - self.session.state[key], False)

    def factory_values(self):
        """{key: value} of Remap Keys and each key the device reports, as from the factory."""
        values = {P.REMAP_KEYS: P.REMAP_REMOTE, **dict(zip(P.KEYS, self.model.keys.factory))}
        return {(P.DEVICE_ADDRESS, i): v for i, v in values.items() if i in self.steppers}

    def to_factory(self):
        s = self.session
        for key, v in self.factory_values().items():
            if s.state.get(key) != v and s.writable(key):
                self.edited.emit(key, v, False)

    def refresh(self):
        session, ready = self.session, self.session.ready()
        if ready:
            self.model = session.model
            self.build(session.device_settings())
        s = session.state
        value = lambda i: s.get((P.DEVICE_ADDRESS, i)) if ready else None          # noqa: E731
        for i, (x, stepper) in self.steppers.items():
            key, v = (P.DEVICE_ADDRESS, i), value(i)
            lines = [key_tip(x, value(P.REMAP_KEYS), v) if i in P.KEYS else tip(self.model, x)]
            faded = i == P.DSD_FILTER and value(P.DSD_DIRECT) == 0
            if faded:
                lines.append(NOT_IN_USE)
            if i in P.KEYS:
                if ready:
                    stepper.names = session.key_names()
                if value(P.REMAP_KEYS) == 0:
                    faded = True
                elif v in self.model.keys.dac_mode and session.basic_mode() != P.MODE_DAC:
                    faded = True
                    lines.append(DAC_MODE_ONLY)
            if i == P.SPDIF_IN and ready and session.basic_mode() == P.MODE_DAC:
                lines.append(NOT_IN_DAC_MODE)
            if key in self.marks.mismatch:
                lines.append("Sent %s, the device has %s." % tuple(stepper.text(n) for n in self.marks.mismatch[key]))
            stepper.show_state(v, session.writable(key), "\n".join(lines), faded, key in self.marks.mismatch)
        if self.factory is not None:
            values = self.factory_values()
            names = session.key_names() if ready else self.model.keys.names
            lines = ["%s: %s" % (self.steppers[i][0].name, names[v] if i in P.KEYS else "Remote")
                     for (_, i), v in values.items()]
            changes = ready and any(s.get(k) != v and session.writable(k) for k, v in values.items())
            self.factory.setEnabled(changes)
            self.factory.setToolTip(FACTORY_TIP % "\n".join(lines) if changes or not ready else AT_FACTORY)
        for i, (x, option) in self.options.items():
            key, on = (P.DEVICE_ADDRESS, i), value(i) == 1
            lines = ["%s: %s" % (x.name, "on" if on else "off"), tip(self.model, x)]
            if i == P.MUTE_V_PH_1_2 and ready and value(P.DUAL_PHONES) != 1:
                lines.append(NEEDS_DUAL_PHONES)
            option.show_state(on, session.writable(key), "\n".join(lines))
