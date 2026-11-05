"""The presets of one output, as the device has them, in three groups:

    the output's name   Load B/T, then Manual and Temp: this output's own, kept by the device rather than the user
    USER                the twenty slots, shared by all outputs
    FACTORY             Clear

A slot's row and Clear are seen before anything is done with them: under the mouse the row opens its preview beside
the panel (the window does that, commander.ui.preview), which has Select, Edit and Store; the row is its tab
meanwhile, on the ground of the preview. A click on such a row does nothing. Manual and Temp, whose content cannot be
seen without selecting them, are selected by a click on their row. The row that is selected on this output carries a
dot; a slot selected on another output carries that output's letter.

Edit opens the slot in the stage and the sound column, apart from the output's EQ (the window does that). Its row
stays in sight meanwhile, as the tab of that page, on the sound column's ground: the name as it is being typed there,
then OK and Cancel, the only ways out; a click on it selects nothing. The name is amber when OK changes more than the
preset (it is selected on an output, or was changed on the device meanwhile), and its tooltip says what: as the name in
the EQ head of an output that has an earlier copy of its preset. When OK cannot be clicked, its tooltip says why.

A row that is being written to the device says so after its name, 'storing…' in amber; that something is being
written, the status bar's lamp says. The row shows its new name at once. A dot in a row only ever means: selected on
this output. When the device reads back otherwise, the row shows what the device has and 'not as sent', with the
difference in its tooltip, until the next action on that row.

    (free)   the slot is unused: selecting it loads the factory state, as Clear
    (lin)    all band gains are 0 dB and no band is a High Pass or High Cut, as the device marks it

Also ChosenRow: the selected row, as the panel draws it, in the EQ head; NameEditor: the name of a preset being
edited, which takes only what the front panel can enter and says so when a key is refused; and SideTab: the tab on
the window's left edge that opens and closes this panel.
"""

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QPainter, QValidator
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QSizePolicy, QToolTip, QVBoxLayout, QWidget

from ..device import params as P
from . import theme
from .widgets import ATTACHED_GAP, GROUP_STYLE, INNER_GAP, TITLE_STYLE, Action, Dot, head, label_color

MANUAL, TEMP, CLEAR = 0, 1, 22                   # EQ Preset Select; Preset n is n + 1
TAGS = {3: "L", 6: "P", 9: "I"}                  # output address -> its letter
TIPS = {MANUAL: "This output's own EQ, apart from the presets.\n"
                "After standby it holds what was selected then: a preset, Temp, or itself.",
        TEMP: "A selected preset, changed.\nStandby moves it into Manual.",
        CLEAR: "The factory state, all bands 0 dB.\n"
               "To reset a preset: select Clear, then Store in the preview of that preset.\n"
               "Store takes this output's Bass/Treble into the preset too."}
NAME_RULE = "Up to %d signs: letters, digits, space and %s" % (P.NAME_LENGTH, " ".join(P.NAME_MARKS))
OK_TIP = "Write this preset to the device as it is now"
STALE_TIP = "This output has an earlier copy of this preset.\nSelect it again to load it as it is now."
BUSY = {"store": "storing…", "write": "storing…"}
NOT_AS_SENT = "not as sent"
ROW_HEIGHT = 24


def describe(result):
    """The differences after a Store or Write, one per line: {key: (sent, actual)}."""
    def name(k):
        return k if isinstance(k, str) else "%d/%d" % k
    return "\n".join("%s: sent %s, the device has %s" % (name(k), sent, actual)
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


class _Row(QWidget):
    def __init__(self, panel, value, slot=None, number=None):
        super().__init__()
        self.panel, self.value, self.slot = panel, value, slot
        self.setFixedHeight(ROW_HEIGHT)
        self.setAttribute(Qt.WA_StyledBackground)
        self.previewable = slot is not None or value == CLEAR      # seen first, in its preview
        self.setCursor(Qt.ArrowCursor if self.previewable else Qt.PointingHandCursor)
        self.dot = Dot()                         # selected on this output
        self.busy = False                        # being written to the device
        self.edited = False                      # open in the edit stand: in sight, but no click selects it
        self.peeked = False                      # its preview is open: the row is its tab
        self.current = False                     # selected on this output
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
        self.ok, self.cancel = Action(compact=True), Action(compact=True)    # in the edit stand
        self.ok.setText("OK")
        self.ok.setToolTip(OK_TIP)
        self.cancel.setText("Cancel")
        self.cancel.setToolTip("Leave the preset on the device as it is")
        self.ok.clicked.connect(lambda: panel.finished.emit(True))
        self.cancel.clicked.connect(lambda: panel.finished.emit(False))
        # name and mark give way: the tags, or OK and Cancel, cover their end, whatever the font
        self.label = QWidget()
        self.label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        label_lay = QHBoxLayout(self.label)
        label_lay.setContentsMargins(0, 0, 0, 0)
        label_lay.setSpacing(6)
        label_lay.addWidget(self.name)
        label_lay.addWidget(self.mark)
        label_lay.addStretch()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(6)
        for w in (self.dot, self.number):
            lay.addWidget(w)
        lay.addWidget(self.label, 1)
        for w in (self.tags, self.ok, self.cancel):
            lay.addWidget(w)
        self.ok.hide()
        self.cancel.hide()

    def text_end(self, tags):
        """Where what the row shows ends, in its own x: its name and mark; with tags, its tags too, when it has
        any."""
        shown = [w for w in (self.name, self.mark) if w.isVisible()]
        if tags and self.tags.text():
            shown.append(self.tags)
        return max(w.mapTo(self, QPoint(w.width(), 0)).x() for w in shown)

    def enterEvent(self, e):
        if self.previewable and self.isEnabled() and not self.edited:
            self.panel.peeked.emit(self.value)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.isEnabled() and not self.edited and not self.previewable:
            self.panel.selected.emit(self.value)

    def set_state(self, name, named, mark, current, tags, enabled, busy="", issue="", edited=False, ok=False,
                  warning="", ok_tip=""):
        """busy: the verb while this row is written to the device; issue: how it read back otherwise; edited: open
        in the edit stand, with name as it is being typed; ok: whether OK can write it now, else ok_tip says why;
        warning: what OK changes beyond the preset."""
        self.name.setText(name)
        self.name.setProperty("named", named)
        plain = theme.TEXT if named and (mark != "(free)" or edited) else theme.SPIN
        restyle(self.name, "color: %s;" % (theme.WARN if edited and warning else plain).name())
        self.label.setToolTip(warning if edited else "")   # not on the amber name: its tooltip would be amber too
        self.plain_mark = mark                   # (free) or (lin), without what is under way
        self.mark.setText(busy or ("" if edited else NOT_AS_SENT if issue else mark))
        restyle(self.mark, label_color(theme.WARN if busy else theme.BAD if issue and not edited else theme.SECONDARY))
        self.mark.setToolTip("" if busy or edited else issue)
        self.busy, self.edited = bool(busy), edited
        self.dot.set(theme.ACCENT) if current else self.dot.clear()
        self.current = current
        self.ground()
        for w in (self.ok, self.cancel):
            w.setVisible(edited and not busy)
        self.ok.setEnabled(ok)
        self.ok.setToolTip(ok_tip if not ok and ok_tip else OK_TIP)
        self.tags.setText(" ".join(tags))
        self.tags.setToolTip("Selected on " + ", ".join(tags) if tags else "")
        self.setCursor(Qt.ArrowCursor if edited or self.previewable else Qt.PointingHandCursor)
        self.setEnabled(enabled or edited)

    def ground(self):
        """As the tab of the edit stand or of a preview: the ground of that page; else selected or not."""
        restyle(self, "_Row { background: %s; border-radius: 3px; }"
                % (theme.BACKGROUND.name() if self.edited or self.peeked else
                   theme.CHOSEN.name() if self.current else "transparent"))


class PresetPanel(QWidget):
    selected = Signal(int)                       # an EQ Preset Select value
    finished = Signal(bool)                      # OK (True) or Cancel in the edit stand
    peeked = Signal(int)                         # the mouse came on a slot's row or Clear: its EQ Preset Select value

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
        lay.addWidget(head(load_bt))                           # per output, and about what Select does here
        lay.addSpacing(ATTACHED_GAP)
        for value in (MANUAL, TEMP):
            self._add(lay, _Row(self, value))
        self._group(lay, "USER")
        for n in range(1, 21):
            self._add(lay, _Row(self, n + 1, n))
        self._group(lay, "FACTORY")
        self._add(lay, _Row(self, CLEAR, number=21))           # RME counts Clear as the 21st entry
        lay.addStretch()

    def peek(self, value):
        """The row whose preview is open (an EQ Preset Select value), or none (None): it is the preview's tab."""
        for row in self.rows.values():
            row.peeked = row.value == value
            row.ground()

    def _add(self, lay, row):
        self.rows[row.value] = row
        row.setToolTip(TIPS.get(row.value, "Shared by all outputs"))
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

    def refresh(self, state, output, slots, ready, operation=None, issues=None, editing=None, tags=None):
        """state: the session's; output: (name, address, left, right) of this tab; slots: as read; operation: the
        Store or Write under way (Session.operation); issues: {slot: how it read back otherwise}; editing: the slot
        open in the edit stand, its name as typed, whether OK can write it now, what OK changes beyond the preset,
        and why OK cannot be clicked; or None; tags: {output address: its mark} of the outputs a preset shows it is
        selected on (default TAGS). Nothing can be clicked while not ready, while an operation is under way, or while
        a slot is edited."""
        name, out, left, _ = output
        tags_of = TAGS if tags is None else tags
        self.output_title.setText(name.upper())
        issues = issues or {}
        enabled = ready and operation is None and editing is None
        chosen = {o: state.get((l, P.EQ_PRESET_SELECT)) for _, o, l, _ in P.OUTPUTS if o in tags_of}
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
            shared = row.slot is not None or value == CLEAR
            tags = [tags_of[o] for o, v in chosen.items() if o != out and v == value] if shared else []
            row.set_state(name, named and (ready or edited), m, ready and chosen.get(out) == value, tags, enabled,
                          busy, describe(issues[row.slot]) if row.slot in issues else "", edited,
                          *(editing[2:] if edited else ()))


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
        lay.setSpacing(6)
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
        self.setToolTip("Show or hide the %s" % text.lower())

    def sizeHint(self):
        fm = self.fontMetrics()
        return QSize(fm.height() + 14, fm.horizontalAdvance(self.text) + 28)

    def minimumSizeHint(self):
        return self.sizeHint()                   # in a narrow window the graph gives way, not the tab

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.set_open(not self.open)

    def set_available(self, on, why=""):
        """Not available: grey, closed and not to be opened, with why as its tooltip."""
        if not on and self.open:
            self.set_open(False)
        self.setEnabled(on)
        self.setCursor(Qt.PointingHandCursor if on else Qt.ArrowCursor)
        self.setToolTip("Show or hide the %s" % self.text.lower() if on else why)

    def set_open(self, on):
        self.open = on
        self.update()
        self.toggled.emit(on)

    def paintEvent(self, e):
        p = QPainter(self)
        if self.open:
            p.fillRect(self.width() - 2, 0, 2, self.height(), theme.ACCENT)
        p.setPen(theme.TEXT if self.open else theme.LABEL if self.isEnabled() else theme.SECONDARY)
        p.translate(0, self.height())
        p.rotate(-90)
        p.drawText(QRect(0, 0, self.height(), self.width()), Qt.AlignCenter, self.text)
