"""The presets of one output, as the device has them, in three groups:

    the output's name   Load B/T, then Manual and Temp: this output's own, kept by the device rather than the user
    USER                the twenty slots, shared by all outputs
    FACTORY             Clear; and Rumble, on a model that has it (Model.rumble)

Under the mouse a row offers what can be done with it (actions): Select over its dot and number, where the dot comes;
for a slot also Edit and Store at its end. A click on the row itself does nothing; a double click is Select, where Select can be
clicked and does what it seems: not where it is amber, nor on an unused slot, where it loads the factory state. The
row's tooltip says so where it applies. A slot's row, Clear and Rumble are also seen
before anything is done with them: meanwhile the window shows their preview over the graph (commander.ui.preview).
Manual and Temp have none: their content cannot be seen without selecting them. The row that is selected on this
output carries a dot; a slot, Clear or Rumble selected on another output carries that output's letter after its name.

Edit opens the slot in the stage and the sound column, apart from the output's EQ (the window does that). Its row
stays in sight meanwhile, as the tab of that page, on the sound column's ground: the name as it is being typed there,
then OK and Cancel, the only ways out; a click on it selects nothing. The name is amber when OK changes more than the
preset (it is selected on an output, or was changed on the device meanwhile), and its tooltip says what: as the name in
the EQ head of an output that has an earlier copy of its preset. When OK cannot be clicked, its tooltip says why.

A row that is being written to the device says so after its name, 'storing…' in amber; that something is being
written, the status bar's lamp says. The row shows its new name at once. A dot in a row only ever means: selected on
this output. When the device reads back otherwise, the row shows what the device has and 'not as sent', with the
difference in its tooltip, until the next action on that row. When the last answer for a slot was incomplete, its
row says 'not read' in amber, with what the answer lacked in its tooltip; a slot read in full before shows that
reading, and when it was.

    (free)   the slot is unused: selecting it loads the factory state, as Clear
    (lin)    all band gains are 0 dB and no band is a High Pass or High Cut, as the device marks it

Also ChosenRow: the selected row, as the panel draws it, in the EQ head; NameEditor: the name of a preset being
edited, which takes only what the front panel can enter and says so when a key is refused; and SideTab: the tab on
the window's left edge that opens and closes this panel.

The row's actions:

    Select      the row becomes this output's source, as the device's EQ Preset Select; also when it is already,
                which loads a preset again as it is now. Amber when it changes more than the preview shows: an unused
                slot, Clear and Rumble switch Bass/Treble on where Load Bass/Treble with preset is on. Its tooltip
                says what it does.
    Edit        opens the edit stand on the slot.
    Store       this output's EQ goes into the slot.

Manual, Temp, Clear and Rumble have Select only: they are no slots.
"""

import time

from PySide6.QtCore import QEvent, QRect, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QValidator
from PySide6.QtWidgets import (QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit, QToolTip, QVBoxLayout,
                               QWidget)

from ..device import params as P
from . import theme
from .widgets import ATTACHED_GAP, GROUP_STYLE, INNER_GAP, TITLE_STYLE, Action, Dot, head, label_color

MANUAL, TEMP, CLEAR, RUMBLE = 0, 1, 22, P.RUMBLE  # EQ Preset Select; Preset n is n + 1
BUILT_IN = (CLEAR, RUMBLE)                       # presets that are no slot: Select only
TAGS = {o: (tag, name) for tag, (name, o, _, _) in zip("LPI", P.OUTPUTS)}   # output address -> its letter, name
INPUT_TAG = "In"                                 # the analog input's mark, on a model that has one
CLEAR_TIP = ("The factory state, all bands 0 dB\n"
             "To reset a preset: select Clear, then Store in the row of that preset.\n")
TIPS = {MANUAL: "This output's own EQ, apart from the presets\n"
                "After standby it holds what was selected then: a preset, Temp, or itself.",
        TEMP: "A selected preset, changed\nStandby moves it into Manual.",
        CLEAR: CLEAR_TIP + "Store takes this output's Bass/Treble into the preset too.",
        RUMBLE: "A rumble filter for a turntable: a high pass at 35 Hz, and -12 dB at 20 Hz"}
CLEAR_INPUT_TIP = CLEAR_TIP + "Store sets the Bass/Treble of the preset to 0 dB."   # the input has no Bass/Treble
NAME_RULE = "Up to %d signs: letters, digits, space and %s" % (P.NAME_LENGTH, " ".join(P.NAME_MARKS))
OK_TIP = "Write this preset to the device as it is now."
STALE_TIP = "This output has an earlier copy of this preset.\nSelect it again to load it as it is now."
BUSY = {"store": "storing…", "write": "storing…"}
NOT_AS_SENT = "not as sent"
NOT_READ_MARK = "not read"
DOUBLE_CLICK_TIP = "Double-click to select it."
EDIT_TIP = "Edit this preset and its name; nothing goes to the device until OK."
EDIT_FREE_TIP = "This preset is unused: it starts as the factory state."
NOT_READ = "Not read from the device yet"
FACTORY = "Select loads the factory state on %s: all bands 0 dB, Dual EQ off."
RUMBLE_LOAD = "Select loads Rumble on %s: a high pass at 35 Hz, -12 dB at 20 Hz, Dual EQ off."
OWN = "Select %s on %s."                         # Manual, Temp: the output's own
ROW_HEIGHT = 24
SPACING = 6                                      # px between what a row shows
TAGS_GAP = 10                                    # px from a name, or its mark, to its tags; a cut name fades there
TAGS_CLEAR = 3                                   # px of that gap where nothing of a cut name shows
INDENT = 8                                       # px from a row's left edge to its dot
ACTION_EDGE = 2                                  # px from a row's edges to its actions: as above and below them


def describe(result):
    """The differences after a Store or Write, one per line: {key: (sent, actual)}."""
    def name(k):
        return k if isinstance(k, str) else "%d/%d" % k
    return "\n".join("%s: sent %s, the device has %s." % (name(k), sent, actual)
                     for k, (sent, actual) in result.items())


def mark(slot):
    """'(free)', '(lin)' or '' for a slot as read; '' while it is not read yet."""
    if slot is None:
        return ""
    if not slot["used"]:
        return "(free)"
    v = slot["vals"]
    gains = all(v.get((a, P.BANDS[b][1])) == 0 for a in (13, 14) for b in P.BANDS)
    passes = any(v.get((a, P.BANDS[b][0])) in types for a in (13, 14) for b, types in P.NO_GAIN_TYPES.items())
    return "(lin)" if gains and not passes else ""


def restyle(widget, sheet):
    """Only when the style changes: setting a style sheet restyles the widget, even the same one."""
    if widget.styleSheet() != sheet:
        widget.setStyleSheet(sheet)


def store_tip(slot, stored, output, others, bt=True):
    """What Store does, a line each. slot: its number; stored: the slot as read, or None; others: the other outputs
    that have the preset selected; bt: this output has Bass/Treble (the input has none)."""
    lines = ["Store the current EQ of %s in Preset %d, %s." % (output, slot, "Bass/Treble included" if bt else
                                                               "with Bass/Treble at 0 dB"),
             "It replaces what the preset holds; the name stays." if stored is None else
             "It replaces what the graph shows; the name stays." if stored["used"] else
             "Preset %d is unused: it becomes used, with the name it shows." % slot]
    selected = "Afterwards Preset %d is selected on %s" % (slot, output)
    lines.append(selected + (" and loaded again on %s" % " and ".join(others) if others else "") + ".")
    return "\n".join(lines)


def select_tip(value, used, current, output, load_bt, bt=True):
    """What Select does on this output, a line each. value: its EQ Preset Select value; bt: this output has
    Bass/Treble (the input has none)."""
    clear = value in BUILT_IN
    if clear:
        first = (RUMBLE_LOAD if value == RUMBLE else FACTORY) % output
    elif not used:
        first = "This preset is unused.\n" + FACTORY % output
    elif current:
        first = "Select it again: %s loads it as it is now." % output
    else:
        first = "Select it on %s: its EQ is loaded there." % output
    if not bt:
        return first
    if not load_bt:
        second = "Bass/Treble stays as it is: Load Bass/Treble with preset is off."
    elif clear or not used:
        second = "Bass/Treble 0 dB and switched on: Load Bass/Treble with preset is on."
    else:
        second = "Its Bass/Treble comes along: Load Bass/Treble with preset is on."
    return first + "\n" + second


def actions(value, stored, output, load_bt, current, others=(), has_bt=True):
    """What a row's actions are now: {'select': (enabled, tooltip, warns), 'edit' and 'store': None where the row has
    none, else (enabled, tooltip)}. value: its EQ Preset Select value; stored: the slot as read, None while not read
    (else not used); output: the name of this output; load_bt: Load Bass/Treble with preset on this output;
    current: selected on this output; others: the other outputs a slot is selected on; has_bt: this output has
    Bass/Treble (the input has none)."""
    if value in (MANUAL, TEMP):
        return {"select": (True, OWN % (P.SOURCES[value], output), False), "edit": None, "store": None}
    clear = value in BUILT_IN
    known = clear or stored is not None
    used = not clear and known and stored["used"]
    select = (known, select_tip(value, used, current, output, load_bt, has_bt) if known else NOT_READ,
              known and not used and load_bt and has_bt)        # the factory state: Bass/Treble switched on
    if clear:
        return {"select": select, "edit": None, "store": None}
    return {"select": select,
            "edit": (known, NOT_READ if not known else EDIT_TIP if used else EDIT_TIP + "\n" + EDIT_FREE_TIP),
            "store": (True, store_tip(value - 1, stored, output, others, has_bt))}


class NameValidator(QValidator):
    """Only what the front panel can enter: its signs, up to 14."""

    def validate(self, text, pos):
        return (QValidator.Acceptable if P.valid_name(text) else QValidator.Invalid), text, pos


class NameEditor(QLineEdit):
    """A preset's name being edited; Escape emits cancelled. A field as a cell of the tables: their ground, their
    grid as its edge, the accent around it while it has the focus."""

    cancelled = Signal()

    def __init__(self):
        super().__init__()
        self.setValidator(NameValidator())
        self.setToolTip(NAME_RULE)
        self.inputRejected.connect(self.explain)
        self.setStyleSheet("QLineEdit { background: %s; color: %s; border: 1px solid %s; padding: 0 3px; }"
                           " QLineEdit:focus { border-color: %s; }"
                           % (theme.CELL.name(), theme.TEXT.name(), theme.GRID.name(), theme.ACCENT.name()))

    def explain(self):
        """A key was refused: say why, at the field."""
        QToolTip.showText(self.mapToGlobal(self.rect().bottomLeft()), NAME_RULE, self)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.cancelled.emit()
            return
        super().keyPressEvent(e)


class _NameLine(QWidget):
    """A row's name and mark, then its tags, TAGS_GAP after them. Short of room the name and mark give way, the tags
    stay whole: what is cut off fades out over that gap, or over as much before the end where there are no tags, and
    is gone TAGS_CLEAR before them. A name that fits ends where the gap begins, so nothing of it fades."""

    def __init__(self, name, mark, tags):
        super().__init__()
        self.name, self.mark, self.tags = name, mark, tags
        self.label = QWidget(self)               # name and mark, cut off at its edge
        for w in (name, mark):
            w.setParent(self.label)
        tags.setParent(self)
        self.fade = QGraphicsOpacityEffect(self.label)
        self.label.setGraphicsEffect(self.fade)

    def _text(self):
        width = self.name.sizeHint().width()
        if self.mark.text():
            width += SPACING + self.mark.sizeHint().width()
        return width

    def _tags(self):
        return self.tags.sizeHint().width() if self.tags.text() else 0

    def sizeHint(self):
        return QSize(self._text() + TAGS_GAP + self._tags(), self.name.sizeHint().height())

    def minimumSizeHint(self):
        return QSize(self._tags() + 1, self.name.sizeHint().height())

    def refit(self):
        """After a change of name, mark or tags."""
        self.updateGeometry()
        self._place()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place()

    def _place(self):
        height, tags = self.height(), self._tags()
        room = self.width() - tags                       # for name, mark and the gap
        self.label.setGeometry(0, 0, room, height)
        width = self.name.sizeHint().width()
        self.name.setGeometry(0, 0, width, height)
        self.mark.setVisible(bool(self.mark.text()))    # empty, it takes no room
        self.mark.setGeometry(width + SPACING, 0, self.mark.sizeHint().width(), height)
        self.tags.setVisible(bool(tags))
        self.tags.setGeometry(room, 0, tags, height)
        gradient = QLinearGradient(room - TAGS_GAP, 0, room - TAGS_CLEAR, 0)
        gradient.setColorAt(0, QColor(0, 0, 0, 255))
        gradient.setColorAt(1, QColor(0, 0, 0, 0))
        self.fade.setOpacityMask(QBrush(gradient))


class _Row(QWidget):
    def __init__(self, panel, value, slot=None, number=None):
        super().__init__()
        self.panel, self.value, self.slot = panel, value, slot
        self.setFixedHeight(ROW_HEIGHT)
        self.setAttribute(Qt.WA_StyledBackground)
        self.previewable = slot is not None or value in BUILT_IN   # has a preview: what it holds can be seen
        self.dot = Dot()                         # selected on this output
        self.busy = False                        # being written to the device
        self.edited = False                      # open in the edit stand: in sight, but its actions are not
        self.current = False                     # selected on this output
        self.tip = ""                            # its tooltip, without the line on a double click
        self.number = QLabel(str(slot or number or ""))
        self.number.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.number.setFont(theme.ui_font(8))
        self.number.setFixedWidth(self.number.fontMetrics().horizontalAdvance("21"))   # the widest number
        self.number.setStyleSheet("color: %s;" % theme.SECONDARY.name())
        self.name = QLabel()
        self.mark = QLabel()
        self.mark.setStyleSheet("color: %s;" % theme.SECONDARY.name())
        self.tags = QLabel()
        self.tags.setFont(theme.ui_font(8))
        self.tags.setStyleSheet("color: %s;" % theme.SPIN.name())
        # the row's actions, while the mouse is on it: Select where the dot comes, the others at the end
        self.select, self.edit, self.store = (Action(compact=True) for _ in range(3))
        self.ok, self.cancel = Action(compact=True), Action(compact=True)    # in the edit stand
        for w, text in ((self.select, "Select"), (self.edit, "Edit"), (self.store, "Store"), (self.ok, "OK"),
                        (self.cancel, "Cancel")):
            w.setText(text)
            w.setFocusPolicy(Qt.NoFocus)         # the actions vanish on a click: the focus stays where it was
            w.hide()
        self.select.setParent(self)
        self.select.installEventFilter(self)
        self.select.clicked.connect(lambda: panel.selected.emit(self.value))
        self.edit.clicked.connect(lambda: panel.edited.emit(self.slot))
        self.store.clicked.connect(lambda: panel.stored.emit(self.slot))
        self.ok.setToolTip(OK_TIP)
        self.cancel.setToolTip("Leave the preset on the device as it is.")
        self.ok.clicked.connect(lambda: panel.finished.emit(True))
        self.cancel.clicked.connect(lambda: panel.finished.emit(False))
        # the dot and the number, as wide as Select over them, which starts nearer the row's edge
        self.lead = QWidget()
        self.select.ensurePolished()
        self.lead.setFixedWidth(self.select.sizeHint().width() - (INDENT - ACTION_EDGE))
        lead_lay = QHBoxLayout(self.lead)
        lead_lay.setContentsMargins(0, 0, 0, 0)
        lead_lay.setSpacing(0)
        lead_lay.addWidget(self.dot)
        lead_lay.addStretch()
        lead_lay.addWidget(self.number)
        # name and mark give way to the tags, and to the actions at the end, whatever the font
        self.line = _NameLine(self.name, self.mark, self.tags)
        self.label = self.line.label
        lay = QHBoxLayout(self)
        lay.setContentsMargins(INDENT, 0, ACTION_EDGE, 0)
        lay.setSpacing(SPACING)
        for w in (self.lead, self.line):
            lay.addWidget(w)
        lay.addStretch(1)
        for w in (self.edit, self.store, self.ok, self.cancel):
            lay.addWidget(w)
        self.select.raise_()                     # over the dot and the number

    def resizeEvent(self, e):
        super().resizeEvent(e)
        size = self.select.sizeHint()
        self.select.setGeometry(ACTION_EDGE, (self.height() - size.height()) // 2, size.width(), size.height())

    def show_actions(self, actions):
        """The row's actions while the mouse is on it, as actions() gives them; None: none."""
        actions = actions or {}
        for key in ("select", "edit", "store"):
            w, state = getattr(self, key), actions.get(key)
            w.setVisible(state is not None)
            if state is None:
                continue
            w.setEnabled(state[0])
            w.setToolTip(state[1])
            if key == "select":
                w.warn(state[2])
        self.set_tip(self.tip)

    def set_tip(self, tip):
        """The row's tooltip; while its actions are shown, with the line on a double click where it applies."""
        self.tip = tip
        self.setToolTip(tip + ("\n" + DOUBLE_CLICK_TIP if self.double_clickable() else ""))

    def double_clickable(self):
        """A double click is Select: where Select is shown and can be clicked, and does what it seems; not on an
        unused slot, where it loads the factory state."""
        return (self.select.isVisibleTo(self) and self.select.isEnabled() and not self.select.warns
                and self.plain_mark != "(free)")

    def eventFilter(self, obj, e):
        if obj is self.select and e.type() in (QEvent.Enter, QEvent.Leave):
            self.panel.aimed.emit(self.value, e.type() == QEvent.Enter)
        return False

    def enterEvent(self, e):
        if self.isEnabled() and not self.edited:
            self.panel.entered.emit(self.value)

    def mouseDoubleClickEvent(self, e):
        """Select, where it applies (double_clickable). A double click on Select itself is one Select: the first
        click hides it."""
        if e.button() == Qt.LeftButton and self.double_clickable():
            self.panel.selected.emit(self.value)

    def set_state(self, name, named, mark, current, tags, enabled, busy="", issue="", edited=False, ok=False,
                  warning="", ok_tip="", unread=""):
        """busy: the verb while this row is written to the device; issue: how it read back otherwise; edited: open
        in the edit stand, with name as it is being typed; ok: whether OK can write it now, else ok_tip says why;
        warning: what OK changes beyond the preset; unread: why its last answer was not read."""
        self.name.setText(name)
        self.name.setProperty("named", named)
        plain = theme.TEXT if named and (mark != "(free)" or edited) else theme.SPIN
        restyle(self.name, "color: %s;" % (theme.WARN if edited and warning else plain).name())
        self.label.setToolTip(warning if edited else "")   # not on the amber name: its tooltip would be amber too
        self.plain_mark = mark                   # (free) or (lin), without what is under way
        self.mark.setText(busy or ("" if edited else NOT_AS_SENT if issue else NOT_READ_MARK if unread else mark))
        restyle(self.mark, label_color(theme.WARN if busy else theme.BAD if issue and not edited else
                                       theme.WARN if unread and not edited else theme.SECONDARY))
        self.mark.setToolTip("" if busy or edited else issue or unread)
        self.busy, self.edited = bool(busy), edited
        self.dot.set(theme.ACCENT) if current else self.dot.clear()
        self.current = current
        self.ground()
        for w in (self.ok, self.cancel):
            w.setVisible(edited and not busy)
        self.ok.setEnabled(ok)
        self.ok.setToolTip(ok_tip if not ok and ok_tip else OK_TIP)
        self.tags.setText(" ".join(tag for tag, _ in tags))
        self.tags.setToolTip(("Also selected on " if current else "Selected on ")    # with the dot: here too
                             + " and ".join(name for _, name in tags) if tags else "")
        self.line.refit()
        self.setEnabled(enabled or edited)

    def ground(self):
        """As the tab of the edit stand: the ground of that page; else selected or not."""
        restyle(self, "_Row { background: %s; border-radius: 3px; }"
                % (theme.BACKGROUND.name() if self.edited else
                   theme.CHOSEN.name() if self.current else "transparent"))


class PresetPanel(QWidget):
    selected = Signal(int)                       # Select in a row: its EQ Preset Select value
    edited = Signal(int)                         # Edit in a slot's row: the slot number
    stored = Signal(int)                         # Store in a slot's row: the slot number
    aimed = Signal(int, bool)                    # the mouse came on (True) or left the Select of a row: its value
    finished = Signal(bool)                      # OK (True) or Cancel in the edit stand
    entered = Signal(int)                        # the mouse came on a row: its EQ Preset Select value

    def __init__(self, load_bt):
        super().__init__()
        title = QLabel("PRESETS")
        title.setStyleSheet(TITLE_STYLE)
        self.rows = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(head(title))
        self.output_title = self._group(lay, "")              # the output's name, as its tab
        self.load_bt_row = head(load_bt)                       # per output, and about what Select does here
        lay.addWidget(self.load_bt_row)
        lay.addSpacing(ATTACHED_GAP)
        for value in (MANUAL, TEMP):
            self._add(lay, _Row(self, value))
        self._group(lay, "USER")
        for n in range(1, 21):
            self._add(lay, _Row(self, n + 1, n))
        self._group(lay, "FACTORY")
        self._add(lay, _Row(self, CLEAR, number=21))           # RME counts Clear as the 21st entry, Rumble the 22nd
        self._add(lay, _Row(self, RUMBLE, number=22))
        self.rows[RUMBLE].hide()
        lay.addStretch()

    def _add(self, lay, row):
        self.rows[row.value] = row
        row.set_tip(TIPS.get(row.value, "Shared by all outputs"))
        lay.addWidget(row)

    @staticmethod
    def _group(lay, name):
        """The title of a group, as in the output panel."""
        title = QLabel(name)
        title.setStyleSheet(GROUP_STYLE)
        lay.addSpacing(INNER_GAP)
        lay.addWidget(head(title))
        lay.addSpacing(ATTACHED_GAP)
        return title

    def refresh(self, state, output, slots, ready, operation=None, issues=None, editing=None, tags=None, unread=None,
                read_at=None):
        """state: the session's; output: (name, address, left, right) of this tab; slots: as read; unread: {slot: why
        its last answer was not read}; read_at: {slot: when it was last read in full, as time.time()}; operation: the
        Store or Write under way (Session.operation); issues: {slot: how it read back otherwise}; editing: the slot
        open in the edit stand, its name as typed, whether OK can write it now, what OK changes beyond the preset,
        and why OK cannot be clicked; or None; tags: {output address: (its mark, its name)} of the outputs a preset
        shows it is selected on (default TAGS). Nothing can be clicked while not ready, while an operation is under
        way, or while a slot is edited."""
        name, out, left, _ = output
        tags_of = TAGS if tags is None else tags
        self.output_title.setText(name.upper())
        self.load_bt_row.setVisible(P.has_bt(out))             # the input has no Bass/Treble
        self.rows[CLEAR].set_tip(TIPS[CLEAR] if P.has_bt(out) else CLEAR_INPUT_TIP)
        issues, unread, read_at = issues or {}, unread or {}, read_at or {}
        enabled = ready and operation is None and editing is None
        chosen = {o: state.get((l, P.EQ_PRESET_SELECT)) for _, o, l, _ in P.CHANNELS if o in tags_of}
        for value, row in self.rows.items():
            busy, edited = "", editing is not None and editing[0] == row.slot
            if row.slot is None:
                name, named, m = P.SOURCES[value], True, ""
            else:
                s = slots.get(row.slot)
                name = s["name"].strip() if s else ""
                if operation is not None and operation[1] == row.slot:
                    busy = BUSY[operation[0]]
                    if operation[2] is not None:
                        name = operation[2].strip()               # the new name, at once
                elif edited:
                    name = editing[1]
                named = bool(name)
                name = name or ("Preset %d" % row.slot if s is None and not edited else "no name")
                m = mark(s)
            shared = row.slot is not None or value in BUILT_IN
            tags = [tags_of[o] for o, v in chosen.items() if o != out and v == value] if shared else []
            why = unread.get(row.slot, "") if row.slot is not None else ""
            if why and row.slot in slots and row.slot in read_at:
                why += "\nShown as read at %s" % time.strftime("%H:%M:%S", time.localtime(read_at[row.slot]))
            row.set_state(name, named and (ready or edited), m, ready and chosen.get(out) == value, tags, enabled,
                          busy, describe(issues[row.slot]) if row.slot in issues else "", edited,
                          *(editing[2:] if edited else (False, "", "")), unread=why)


class ChosenRow(QWidget):
    """What this output's EQ is loaded from, drawn as its row in the presets panel: the dot, the number, the name
    and (free) or (lin), on the background of a selected row. Not 'storing…' or 'not as sent': those stay in the
    panel. Its own: the name in amber when this output has an earlier copy of the preset, which is about this
    output rather than the slot."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(ROW_HEIGHT)
        self.setAttribute(Qt.WA_StyledBackground)
        self.setStyleSheet("ChosenRow { background: %s; border-radius: 3px; }" % theme.CHOSEN.name())
        self.dot = Dot()
        self.dot.set(theme.ACCENT)
        self.number = QLabel()
        self.number.setFont(theme.ui_font(8))
        self.number.setStyleSheet("color: %s;" % theme.SECONDARY.name())
        self.name = QLabel()
        self.mark = QLabel()
        self.mark.setStyleSheet("color: %s;" % theme.SECONDARY.name())
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(SPACING)
        for w in (self.dot, self.number, self.name, self.mark):
            lay.addWidget(w)

    def copy(self, row, stale=False):
        """The look of this row of the panel, or nothing (None); stale: this output has an earlier copy of it."""
        self.setVisible(row is not None)
        if row is None:
            return
        self.number.setText(row.number.text())
        self.number.setVisible(bool(row.number.text()))
        self.name.setText(row.name.text())
        self.name.setStyleSheet("color: %s;" % theme.WARN.name() if stale else row.name.styleSheet())
        self.setToolTip(STALE_TIP if stale else "")
        self.mark.setText(row.plain_mark)
        self.mark.setVisible(bool(row.plain_mark))


class SideTab(QWidget):
    """A tab on the window's left edge, its text upright from bottom to top; open: its panel is shown."""

    toggled = Signal(bool)

    def __init__(self, text):
        super().__init__()
        self.text, self.open = text, False
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Show or hide the %s." % text.lower())

    def sizeHint(self):
        fm = self.fontMetrics()
        return QSize(fm.height() + 14, fm.horizontalAdvance(self.text) + 28)

    def minimumSizeHint(self):
        return self.sizeHint()                   # in a narrow window the graph gives way, not the tab

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.set_open(not self.open)

    def set_open(self, on):
        self.open = on
        self.update()
        self.toggled.emit(on)

    def paintEvent(self, e):
        p = QPainter(self)
        if self.open and self.isEnabled():
            p.fillRect(self.width() - 2, 0, 2, self.height(), theme.ACCENT)
        p.setPen(theme.TEXT if self.open else theme.LABEL if self.isEnabled() else theme.SECONDARY)
        p.translate(0, self.height())
        p.rotate(-90)
        p.drawText(QRect(0, 0, self.height(), self.width()), Qt.AlignCenter, self.text)
