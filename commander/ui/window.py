"""The main window: output tabs; on the left edge the output's other settings and the presets, each opened and
closed by its tab; the response graph, which takes the room left; beside it, one under the other, what shapes the
sound: the parametric EQ (a table per channel; with Dual EQ off both show the one EQ of both channels, in the
shared colour), Bass/Treble, and Loudness with a graph of what it does; and a status bar with the connection.

One title, EQ, over the column, with what the EQ was loaded from and, on the right, Save and Load of the EQ of
this output as a file. Close above the tables Dual EQ: Share L > R and Share R > L, or Split L <> R. Below that each
part is a table headed by its own switch, in the corner above the row names, on the line of the column names:
a state is shown once, where it is set. Room between the parts groups them: less between the two channels than
between the EQ, Bass/Treble and Loudness.

A preset's row, or Clear, under the mouse opens its preview (PresetPreview) just past the names in the presets panel,
joined to the row as its tab, with Select, Edit and Store; the row of its actions lies level with the row where there
is room. It stays open while the mouse is on the row, on the preview, or between them, follows the mouse to another
such row, and closes when an action is clicked.

Edit in a preset's preview opens the edit stand: the stage and the column show the preset (a Draft) instead of the
output's EQ, and all else lies under a veil (Scrim), out of reach, with the row joined to them as their tab. The title
is PRESET, with the number and the name, which can be typed; the switches are titles, as a preset has none; Loudness,
no part of a preset, is gone. Save and Load work on the preset; nothing goes to the device. Nothing is chosen at the
start: no link with the work before, which is back afterwards. OK and Cancel, the only ways out, are in the preset's
row; its name is amber when OK changes more than the preset, its tooltip says what. OK writes the preset as a whole
and leaves once the device has it; it can be clicked only when the preset is changed. Cancel leaves without
writing."""

import datetime
import os

from PySide6.QtCore import QModelIndex, QPoint, QRect, QRectF, QSettings, QSize, QStandardPaths, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QFont, QIcon, QKeySequence, QPainter, QPalette, QShortcut
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel,
                               QMainWindow, QMessageBox, QScrollArea, QStackedWidget, QTabBar, QVBoxLayout,
                               QWidget)

from .. import __version__
from .. import backup
from ..conversion import setupfile
from ..conversion import eqfile as E
from ..conversion import eqimport as I
from ..conversion import presetfile as R
from ..device import models
from ..device import params as P
from ..draft import Draft
from . import theme
from .about import AboutDialog
from .graph import LEGEND_GAP, SAMPLE_RATES, TITLE_ROOM, ZONE_INK, ResponseGraph, side_color
from .inputs import InputPanel
from .legend import ITEM_PAD, Legend
from .loaddialog import LoadDialog, read_file
from .loudness import LoudnessGraph
from .output import OutputPanel
from .presets import ChosenRow, NameEditor, PresetPanel, SideTab
from .preview import PresetPreview
from .scrim import RISE, Scrim
from . import untested
from .tables import (BAND_COLUMNS, BAND_WIDTHS, BT_COLUMNS, BT_WIDTHS, LOUDNESS_COLUMNS, CellDelegate, Marks,
                     ParamModel, ParamView, band_address, band_rows, bt_rows, loudness_rows)
from .widgets import (ATTACHED_GAP, DOT, DOT_GAP, INNER_GAP, SECTION_GAP, SIDE, TITLE_STYLE, Action, InfoButton, Option,
                      Switch, Choice, dot_icon, dot_pixmap, dropped_file, head, label_color, pulse, switch_tip)

FS_TIP = "Sample rate the curves are computed at"
ACTIVE_TIP = "Active on the device: its display and volume knob are on this output."
ACTIVE = "Active on the device"                 # the ADI-2 Pro and ADI-2/4 Pro
ALWAYS_ACTIVE = "Always active on the device"
NOT_YET = "Not yet available for the %s"          # with the model's name
# the kinds of file Save writes
APO_FILES = "Equalizer APO (*.txt)"
REMOTE_FILES = "ADI-2 Remote preset (*.adieqpr)"
REMOTE_SUFFIX = ".adieqpr"
ONE_EQ = "EQ on one stereo channel only"
ONE_EQ_TIP = ("From %g kHz the %s runs the EQ on one stereo channel only: the input, Line Out or Phones 3/4.\n"
              "It may not be this output.")
LAMP = {"searching": (theme.SECONDARY, "Waiting for the device"), "busy": (theme.WARN, "Port in use"),
        "loading": (theme.WARN, "Reading"), "ready": (theme.GOOD, "Connected"),
        "unsupported": (theme.WARN, "%s not currently supported")}      # with the model's name
EQ_OWN = ("EQ LEFT", "EQ RIGHT")
# a thin space around the sign between the channels
EQ_SHARED = ("EQ L = R", "EQ R = L")
SHARE = ("Share L > R", "Share R > L")
SPLIT = "Split L <> R"

BT_IN_PRESET = "Bass/Treble of this preset: it comes along only where Load Bass/Treble with preset is on"
PREVIEW_GAP = 16                                 # px from the end of the longest name to a preset's preview
PREVIEW_INSET = 8                                # px in from the graph's zone: the preview no further right, nor higher


class Lamp(QWidget):
    """A coloured dot, the state of the connection; while writes are on their way it pulses in amber."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(14, 14)
        self.color, self.busy, self.phase = theme.SECONDARY, False, 0

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QColor(theme.WARN if self.busy else self.color)
        if self.busy:
            c.setAlphaF(pulse(self.phase))
        p.setBrush(c)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF((self.width() - DOT) / 2, (self.height() - DOT) / 2, DOT, DOT))   # as every dot


class GraphHead(QWidget):
    """The line above the graph: the legend of the graph shown in the middle, the sample rates on the right. When
    both do not fit on one line, the legend's groups go one under the other, the sample rates beside the first; when
    that does not fit either, the sample rates go on a line of their own, above the legend, and all of it on the
    right: the names end where kHz ends. As high as the highest of the legends needs, so the graph does not move
    when the other one takes the stage."""

    GAP = 24
    ABOVE_GAP = 8                                # under the sample rates, over the legend

    def __init__(self, legend, controls, others=()):
        super().__init__()
        self.legend, self.controls = legend, controls
        self.legends = [legend, *others]
        for other in self.legends:
            other.setParent(self)
            other.setVisible(other is legend)
        controls.setParent(self)
        self._sizes = None

    def set_legend(self, legend):
        """The legend of the other graph, in the place of this one."""
        if legend is self.legend:
            return
        self.legend.hide()
        legend.show()
        self.legend = legend
        self.refit()

    def refit(self):
        """After a legend or the note changed: place them again, and lay out the window again only when their
        size changed, not on every refresh (a new layout during a drag in the graph would get in its way)."""
        sizes = [(l.size_for(False), l.size_for(True)) for l in self.legends] + [self.controls.sizeHint()]
        if sizes != self._sizes:
            self._sizes = sizes
            self.updateGeometry()
        self.place()

    def _fit(self, width, legend):
        """'line': all on one line; 'rows': the legend's groups one under the other, the sample rates beside them;
        'above': the sample rates over the legend, which is on one line if that fits."""
        c = self.controls.sizeHint().width()
        if legend.size_for(False).width() + self.GAP + c <= width:
            return "line", False
        if legend.size_for(True).width() + self.GAP + c <= width:
            return "rows", True
        return "above", legend.size_for(False).width() > width

    def _lead(self, legend):
        """How far the legend goes down, and the sample rates, so that they share the middle of the first line."""
        h0, ch = legend.first_row_height(), self.controls.sizeHint().height()
        return max(0, (ch - h0) // 2), max(0, (h0 - ch) // 2)

    def _height(self, width, legend):
        how, stacked = self._fit(width, legend)
        lh, ch = legend.size_for(stacked).height(), self.controls.sizeHint().height()
        if how == "above":
            return ch + self.ABOVE_GAP + lh
        legend_y, controls_y = self._lead(legend)
        return max(legend_y + lh, controls_y + ch)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return max(self._height(width, legend) for legend in self.legends)

    def sizeHint(self):
        c = self.controls.sizeHint()
        return QSize(self.legend.size_for(False).width() + self.GAP + c.width(),
                     max([l.size_for(False).height() for l in self.legends] + [c.height()]))

    def minimumSizeHint(self):
        """Not the legend's width: it changes with what the graph shows (EQ Right only with Dual EQ), and the
        window would grow while one works in it. The graph's own minimum is wider than the legend."""
        c = self.controls.sizeHint()
        return QSize(c.width(), max([l.size_for(False).height() for l in self.legends] + [c.height()]))

    def resizeEvent(self, e):
        self.place()

    def place(self):
        w = self.width()
        how, stacked = self._fit(w, self.legend)
        self.legend.set_stacked(stacked, right=how == "above")
        l, c = self.legend.size_for(stacked), self.controls.sizeHint()
        if how == "above":
            self.controls.setGeometry(w - c.width(), 0, c.width(), c.height())
            x = w - l.width() + ITEM_PAD                 # the room after the last name over the edge
            self.legend.setGeometry(x, c.height() + self.ABOVE_GAP, l.width(), l.height())
            return
        legend_y, controls_y = self._lead(self.legend)
        x = min((w - l.width()) // 2, w - c.width() - self.GAP - l.width())
        self.legend.setGeometry(x, legend_y, l.width(), l.height())
        self.controls.setGeometry(w - c.width(), controls_y, c.width(), c.height())




class MainWindow(QMainWindow):
    PRESETS_WIDTH = 260
    LOUDNESS_WIDTHS = [88, 88, 88]

    def __init__(self, session, simulated=False, settings=None, backups=None):
        """simulated: the session talks to the simulator; settings: a QSettings for what the app remembers (default
        the user's, untested.ORGANIZATION and APPLICATION); backups: the folder for a copy of the device's state at
        each connection (backup.keep), or None for none."""
        super().__init__()
        self.session = session
        self.simulated = simulated
        self.backups = backups
        self.taken = None                            # the state as connected, (state, model), until saved
        self.settings = settings if settings is not None else QSettings(untested.ORGANIZATION, untested.APPLICATION)
        self.warned = set()                          # the untested models the notice was shown for in this run
        self.marks = Marks()
        self.slot_issues = {}                        # {slot: {key: (sent, actual)}} after a Store or Write
        self.draft = None                            # the preset open in the edit stand
        self.before_edit = None                      # where the work was when it opened: see leave_edit
        self.draft_marks = Marks()                   # its flashes; nothing of it is read back
        self.draft_marks.on_flash = self.marks.on_flash
        self.preview_row = None                      # the row whose preview is open
        self.pointer = QCursor.pos                   # where the mouse is, on the screen
        self.setWindowTitle("ADI-2 Commander")

        # top: output tabs; the connection is in the status bar
        self.model = models.DAC                          # the model the window is laid out for: the last connected
        self.tabs = QTabBar()
        for name in self.model.outputs:
            self.tabs.addTab(name)
        self.tabs.currentChanged.connect(self.set_output)
        self.tabs.setIconSize(QSize(DOT + DOT_GAP, DOT))
        self.no_dot = QIcon(dot_pixmap(theme.GOOD, True, alpha=0, gap=DOT_GAP))   # a dot's room, so no tab moves
        self.dot = dot_icon(theme.GOOD, True)
        self.dot.addPixmap(dot_pixmap(theme.GOOD, True, gap=DOT_GAP), QIcon.Disabled)   # a fact: not greyed out
        top = QHBoxLayout()
        top.addWidget(self.tabs)
        top.addStretch()
        self.info = InfoButton(self.tabs)                # about the app; F1 too
        self.info.setToolTip("About ADI-2 Commander (F1)")
        self.info.clicked.connect(self.show_about)
        top.addWidget(self.info)
        QShortcut(QKeySequence(Qt.Key_F1), self, self.show_about)
        self.lamp = Lamp()
        self.lamp_text = QLabel()
        bar = self.statusBar()
        bar.setSizeGripEnabled(False)
        bar.addWidget(self.lamp)
        bar.addWidget(self.lamp_text)
        # beside the connection: what comes in, as facts side by side
        self.input_text, self.rate_text = QLabel(), QLabel()
        self.input_text.setToolTip("The input of all outputs (Source)")
        self.rate_text.setToolTip("The sample rate the device runs at, and PCM or DSD")
        self.signal_info = QWidget()
        signal_lay = QHBoxLayout(self.signal_info)
        signal_lay.setContentsMargins(INNER_GAP, 0, 0, 0)
        signal_lay.setSpacing(INNER_GAP)
        self.one_eq = QLabel(ONE_EQ)                     # ADI-2 Pro and ADI-2/4 Pro at a high rate: show_own_rate
        self.one_eq.setStyleSheet(label_color(theme.WARN))
        self.one_eq.hide()
        signal_lay.addWidget(self.input_text)
        signal_lay.addWidget(self.rate_text)
        signal_lay.addWidget(self.one_eq)
        bar.addWidget(self.signal_info)
        self.file_note = QLabel()                        # what the last Save or Load did
        self.file_note.setContentsMargins(0, 0, 8, 0)    # as far from the edge as the lamp on the left
        bar.addPermanentWidget(self.file_note)
        self.folder = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        self.setAcceptDrops(True)                        # a filter file dropped on the window: Load

        # bands: a table per channel, one under the other; with Dual EQ off both show the one EQ of both channels
        self.band_models, self.band_delegates, self.band_views = [], [], []
        for side in (0, 1):
            m = ParamModel(session, self.marks, band_rows(side), BAND_COLUMNS)
            d = CellDelegate(m, self.marks, side_color(side, True))
            v = ParamView(m, d)
            self.band_models.append(m)
            self.band_delegates.append(d)
            self.band_views.append(v)
        # the EQ head: title and what the EQ was loaded from; under it the actions on the EQ; each table: its switch
        self.eq_title = QLabel("EQ")
        self.eq_title.setStyleSheet(TITLE_STYLE)
        self.source = ChosenRow()                        # as the selected row in the presets panel
        self.save_action, self.load_action = Action(), Action()
        self.save_action.setText("Save…")
        self.save_action.setToolTip("Save the EQ of this output to a file")
        self.save_action.clicked.connect(self.save_dialog)
        self.load_action.setText("Load…")
        self.load_action.setToolTip("Load filters (Equalizer APO, REW, other) or a curve into this output\n"
                                    "Or drop a filter file or a curve on the window.")
        self.load_action.clicked.connect(self.load_dialog)
        self.eq_switches = [Switch(name) for name in EQ_OWN]     # colours as in the graph
        self.dual_actions = [Action(), Action()]
        for side in (0, 1):
            self.eq_switches[side].clicked.connect(lambda _=False, side=side: self.toggle_eq(side))
            self.dual_actions[side].clicked.connect(lambda _=False, side=side: self.dual_action(side))
            self.band_views[side].set_corner(self.eq_switches[side])

        # Bass/Treble: shared by both channels; its switch in the table's corner, as a channel's, in its graph colour.
        # Its row labels take the width of the band Type column too: Freq, Gain and Q line up with the bands'
        under_bands = ParamView.HEADER_WIDTH + BAND_WIDTHS[0]
        self.bt_model = ParamModel(session, self.marks, bt_rows, BT_COLUMNS)
        self.bt_delegate = CellDelegate(self.bt_model, self.marks, theme.BT)
        self.bt_view = ParamView(self.bt_model, self.bt_delegate, under_bands)
        self.bt_switch = Switch("BASS/TREBLE", theme.BT)
        self.bt_switch.clicked.connect(self.toggle_bt)
        self.bt_view.set_corner(self.bt_switch)

        # Loudness: on the output address, for both channels; volume dependent, so not in the response graph,
        # but in its own in the response graph's place while one works in the table: the boost against the volume
        self.loudness_model = ParamModel(session, self.marks, loudness_rows, LOUDNESS_COLUMNS)
        self.loudness_delegate = CellDelegate(self.loudness_model, self.marks, theme.LOUDNESS)
        self.loudness_view = ParamView(self.loudness_model, self.loudness_delegate, under_bands)
        self.loudness_graph = LoudnessGraph()
        self.loudness_graph.edited.connect(self.write)
        self.loudness_graph.picked.connect(self.select_cell)
        self.loudness_switch = Switch("LOUDNESS", theme.LOUDNESS)
        self.loudness_switch.clicked.connect(self.toggle_loudness)
        self.loudness_view.set_corner(self.loudness_switch)

        # the response graph, with what it shows spelled out above it
        self.graph = ResponseGraph(session)
        self.graph.setMinimumSize(360, 300)
        self.graph.edited.connect(self.write)
        self.graph.picked.connect(self.select_cell)
        self.legend = Legend(self.graph)
        self.graph_note = QLabel()
        self.graph_note.setStyleSheet("color: %s;" % theme.SECONDARY.name())
        self.fs_box = Choice()
        for fs in SAMPLE_RATES:
            self.fs_box.addItem("%g" % (fs / 1000), fs)                 # the unit beside the list
        self.fs_unit = QLabel("kHz")
        self.fs_unit.setStyleSheet("color: %s;" % theme.LABEL.name())
        self.fs_box.setCurrentIndex(SAMPLE_RATES.index(self.graph.fs))
        self.fs_box.setToolTip(FS_TIP)
        self.live_shown = None                           # see show_live_rate
        self.before_switch = None                        # where the focus was before a switch took it: see on_focus
        self.fs_label = QLabel("<i>f</i><sub>s</sub>")
        self.fs_label.setTextFormat(Qt.RichText)
        self.fs_label.setStyleSheet("color: %s;" % theme.LABEL.name())
        self.fs_label.setBuddy(self.fs_box)
        self.fs_box.currentIndexChanged.connect(self.set_fs)
        for side, v in enumerate(self.band_views):
            v.selectionModel().currentChanged.connect(lambda idx, _, side=side: self.on_current(side, idx))
        self.bt_view.selectionModel().currentChanged.connect(lambda idx, _: self.on_current(None, idx))
        self.loudness_view.selectionModel().currentChanged.connect(lambda idx, _: self.on_loudness_current(idx))
        QApplication.instance().focusChanged.connect(self.on_focus)   # into a table whose current cell stays

        for d in self.band_delegates + [self.bt_delegate, self.loudness_delegate]:
            d.edited.connect(self.write)
        for v in self.band_views + [self.bt_view, self.loudness_view]:
            v.stepped.connect(self.write)
            v.tabbed.connect(lambda direction, v=v: self.tab_to(v, direction))
            v.walked_off.connect(lambda direction, column, v=v: self.walk_on(v, direction, column))
        QShortcut(QKeySequence("Ctrl+Tab"), self, lambda: self.next_tab(1))
        QShortcut(QKeySequence("Ctrl+Shift+Tab"), self, lambda: self.next_tab(-1))

        # the sound, one part under the other: the EQ, Bass/Treble, Loudness; it scrolls when the window is low
        sound = QVBoxLayout()
        sound.setContentsMargins(0, 0, 0, 0)
        sound.setSpacing(0)                              # only the gaps below
        self.source.setFixedHeight(self.save_action.sizeHint().height())   # as high as Save and Load beside it
        # in the edit stand: the preset's number and its name, to be typed, in the place of the source
        self.preset_number = QLabel()
        self.preset_number.setStyleSheet("color: %s;" % theme.SECONDARY.name())
        self.preset_name = NameEditor()
        self.preset_name.setFixedHeight(self.save_action.sizeHint().height())
        self.preset_name.setFixedWidth(self.preset_name.fontMetrics().horizontalAdvance("W" * 10) + 12)
        self.preset_name.textEdited.connect(self.rename_draft)
        self.preset_name.cancelled.connect(self.restore_name)
        for w in (self.preset_number, self.preset_name):
            w.hide()
        title = head(self.eq_title, self.source, self.preset_number, self.preset_name)   # Save and Load on the title
        title.layout().addWidget(self.save_action)       # line, as they act on the EQ
        title.layout().addWidget(self.load_action)
        sound.addWidget(title)
        sound.addSpacing(INNER_GAP)
        sound.addWidget(head(*self.dual_actions))        # Share and Split; Split takes the place of Share L
        sound.addSpacing(ATTACHED_GAP)
        sound.addWidget(self.band_views[0])
        sound.addSpacing(INNER_GAP)
        sound.addWidget(self.band_views[1])
        sound.addSpacing(SECTION_GAP)
        sound.addWidget(self.bt_view)
        sound.addSpacing(SECTION_GAP)
        sound.addWidget(self.loudness_view)
        sound.addStretch(1)
        sound_widget = QWidget()
        sound_widget.setLayout(sound)
        self.sound = QScrollArea()
        self.sound.setWidget(sound_widget)
        self.sound.setWidgetResizable(True)
        self.sound.setFrameShape(QFrame.NoFrame)
        self.sound.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # the stage: the response graph, or the Loudness graph while one works in its table; its legend and the
        # sample rates above it
        controls = QWidget()
        controls_lay = QHBoxLayout(controls)
        controls_lay.setContentsMargins(0, 0, 0, 0)
        controls_lay.addWidget(self.graph_note)
        controls_lay.addSpacing(10)
        controls_lay.addWidget(self.fs_label)
        controls_lay.addWidget(self.fs_box)
        controls_lay.addWidget(self.fs_unit)
        self.graph_head = GraphHead(self.legend, controls, [self.loudness_graph.legend])
        graph_side = QVBoxLayout()
        graph_side.setSpacing(LEGEND_GAP)
        graph_side.addWidget(self.graph_head)
        self.stage = QStackedWidget()
        self.stage.addWidget(self.graph)
        self.stage.addWidget(self.loudness_graph)
        graph_side.addWidget(self.stage, 1)

        # the presets: on the left edge, opened and closed by their tab
        self.load_bt = Option("Load Bass/Treble with preset")      # RME's name for it, in full
        self.load_bt.clicked.connect(self.toggle_load_bt)
        self.presets = PresetPanel(self.load_bt)
        self.presets.selected.connect(self.select_preset)
        self.presets.finished.connect(self.finish_edit)
        self.presets.peeked.connect(self.open_preview)
        self.presets_area = QScrollArea()
        self.presets_area.setWidget(self.presets)
        self.presets_area.setWidgetResizable(True)
        self.presets_area.setFrameShape(QFrame.NoFrame)
        self.presets_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.presets_area.setFixedWidth(self.PRESETS_WIDTH)
        self.presets_area.hide()
        self.presets_tab = SideTab("PRESETS")
        self.presets_tab.toggled.connect(self.presets_area.setVisible)
        # the output's other settings: on the left edge too, before the presets
        self.output_panel = OutputPanel(session, self.marks)
        self.output_panel.edited.connect(self.write)
        self.output_area = QScrollArea()
        self.output_area.setWidget(self.output_panel)
        self.output_area.setWidgetResizable(True)
        self.output_area.setFrameShape(QFrame.NoFrame)
        self.output_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.output_area.setFixedWidth(self.PRESETS_WIDTH)
        self.output_area.hide()
        self.output_tab = SideTab("OUTPUT")
        self.output_tab.toggled.connect(self.output_area.setVisible)
        # the input, of the whole device: first, where the signal comes in
        self.input_panel = InputPanel(session, self.marks)
        self.input_area = QScrollArea()
        self.input_area.setWidget(self.input_panel)
        self.input_area.setWidgetResizable(True)
        self.input_area.setFrameShape(QFrame.NoFrame)
        self.input_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.input_area.setFixedWidth(self.PRESETS_WIDTH)
        self.input_area.hide()
        self.input_tab = SideTab("INPUT")
        self.input_tab.toggled.connect(self.input_area.setVisible)
        # a line between two open panels: they stand on the same ground
        self.panel_lines = []
        for _ in range(2):
            line = QFrame()
            line.setFixedWidth(1)
            line.setStyleSheet("background: %s;" % theme.GRID.name())
            line.hide()
            self.panel_lines.append(line)
        for tab in (self.input_tab, self.output_tab, self.presets_tab):
            tab.toggled.connect(self.show_panel_lines)
        strip = QVBoxLayout()
        strip.addWidget(self.input_tab)
        strip.addWidget(self.output_tab)
        strip.addWidget(self.presets_tab)
        strip.addStretch()

        # the graph's zone, darker than the columns beside it, from the tabs down to the status bar; beside it
        # everything stays as far from the tabs and the status bar, and inside it the head too; the plot with its axes
        # is as far from the zone's edge on the other three sides
        below_tabs, above_status = 6, 8
        display = QWidget()
        display.setLayout(graph_side)
        graph_side.setContentsMargins(ZONE_INK - TITLE_ROOM[0], below_tabs, ZONE_INK, ZONE_INK - TITLE_ROOM[1])
        display.setAutoFillBackground(True)
        ground = display.palette()
        ground.setColor(QPalette.Window, theme.DISPLAY)
        display.setPalette(ground)
        left = QHBoxLayout()
        left.setContentsMargins(0, below_tabs, 0, above_status)
        left.setSpacing(16)
        left.addLayout(strip)
        left.addWidget(self.input_area)
        left.addWidget(self.panel_lines[0])
        left.addWidget(self.output_area)
        left.addWidget(self.panel_lines[1])
        left.addWidget(self.presets_area)
        right = QVBoxLayout()
        right.setContentsMargins(0, below_tabs, 0, above_status)
        right.setSpacing(0)
        right.addWidget(self.sound)
        main = QHBoxLayout()
        main.setSpacing(16)
        main.addLayout(left)
        main.addWidget(display, 1)                       # all extra room goes to the graph
        self.display = display
        main.addLayout(right)

        # as far from the right edge as from the left: the tables, Load… and the ring; the scroll bar of a low window
        # goes in that margin, against the edge
        body = QVBoxLayout()
        body.setContentsMargins(SIDE, 8, 0, 0)
        body.setSpacing(0)
        top.addSpacing(SIDE)
        body.addLayout(top)
        body.addLayout(main, 1)
        root = QWidget()
        root.setLayout(body)
        self.setCentralWidget(root)
        self.scrim = Scrim(root)
        self.preview = PresetPreview(root)
        self.preview.selected.connect(lambda value: self.from_preview(self.select_preset, value))
        self.preview.edited.connect(lambda slot: self.from_preview(self.edit_preset, slot))
        self.preview.stored.connect(lambda slot: self.from_preview(self.store_preset, slot))
        self.peek = Scrim(root)                          # the preview's outline and tab
        self.peek.veil = False
        self.peek.margin = 0

        session.on_connection.append(self.on_connection)
        session.on_changed.append(self.on_changed)
        session.on_verified.append(self.on_verified)
        session.on_slots.append(lambda numbers: self.refresh_slots())
        session.on_slots.append(lambda numbers: self.save_backup())
        session.on_stale.append(lambda outputs: self.refresh_presets())
        session.on_operation.append(self.on_operation)
        session.on_device_status.append(self.on_device_status)
        self.set_output(0)
        self.set_model(self.model)
        for v in self.band_views:
            v.fit(BAND_WIDTHS)
        self.bt_view.fit(BT_WIDTHS)
        self.loudness_view.fit(self.LOUDNESS_WIDTHS)
        # the column is as wide as a band table, so all of it ends on one line; the scroll bar goes in the margin
        width = self.band_views[0].width()
        self.sound.widget().setFixedWidth(width)
        self.sound.setFixedWidth(width + max(SIDE, self.sound.verticalScrollBar().sizeHint().width()))
        self.on_connection(session.status or "searching", "")

        self.timer = QTimer(self, interval=20, timeout=self.tick)
        self.timer.start()

    def closeEvent(self, e):
        if self.draft is not None and self.draft.changed() and not self.discard_ok():
            e.ignore()                                   # back to the preset being edited
            return
        self.timer.stop()                                # a closed window no longer talks to the device
        super().closeEvent(e)

    def discard_ok(self):
        """Closing while a changed preset is open: whether its changes may go."""
        box = QMessageBox(QMessageBox.Warning, "Preset %d" % self.draft.slot,
                          "Preset %d has changes that are not stored." % self.draft.slot, parent=self)
        box.setInformativeText("Close and lose them?")
        discard = box.addButton("Discard and close", QMessageBox.DestructiveRole)
        box.setDefaultButton(box.addButton("Keep editing", QMessageBox.RejectRole))
        box.exec()
        return box.clickedButton() is discard

    # -- session events -----------------------------------------------------------------------
    def tick(self):
        self.session.tick()
        self.output_panel.volume.tick(self.session.clock())  # a held Volume arrow repeats on the session's clock
        self.lamp.busy = bool(self.session.pending or self.session.sent or self.session.operating())
        self.lamp.phase += 1
        self.lamp.update()
        if self.preview_row is not None:
            self.follow_preview(self.pointer())

    def set_model(self, model):
        """Lay the window out for a model: the names of the outputs; an output, and the panels of the input and the
        output's other settings, that Commander does not control on it are grey and cannot be opened."""
        self.model = model
        self.graph.no_bt_from = self.loudness_graph.no_bt_from = self.preview.no_bt_from = model.no_bt_from
        why = NOT_YET % model.name
        for i, (name, (_, out, _, _)) in enumerate(zip(model.outputs, P.OUTPUTS)):
            self.tabs.setTabText(i, name)
            self.tabs.setTabEnabled(i, out in model.controlled)
        for tab in (self.input_tab, self.output_tab):
            tab.set_available(not model.eq_only, why)
        if self.output[1] not in model.controlled:
            self.tabs.setCurrentIndex(next(i for i, o in enumerate(P.OUTPUTS) if o[1] in model.controlled))
        self.on_device_status(self.session.device_status)

    def on_connection(self, status, detail):
        if status == "ready" and self.session.model != self.model:
            self.set_model(self.session.model)
        if status == "ready":
            if self.backups is not None:             # before anything can be written
                self.taken = (dict(self.session.state), self.session.model)
            QTimer.singleShot(0, self.warn_untested)    # after this event: the notice is modal
        else:
            self.taken = None
        color, text = LAMP[status]
        if status == "unsupported":
            text %= self.session.model.name
        self.lamp.color = color
        self.lamp_text.setText(text)
        self.lamp_text.setToolTip(detail)
        if status != "ready":
            self.marks.mismatch.clear()
        self.refresh()

    def on_device_status(self, status):
        """An output the device has active gets a dot on its tab, in the colour of the lamp: a fact of the device,
        not a choice here; also on an output Commander does not control."""
        active = self.model.active[status.output] if status is not None else ()
        always = set.intersection(*map(set, self.model.active))
        for i, (_, out, _, _) in enumerate(P.OUTPUTS):
            on = out in active
            self.tabs.setTabIcon(i, self.dot if on else self.no_dot)
            tip = ACTIVE_TIP if not self.model.eq_only else ALWAYS_ACTIVE if out in always else ACTIVE
            tips = ([] if self.tabs.isTabEnabled(i) else [NOT_YET % self.model.name]) + ([tip] if on else [])
            self.tabs.setTabToolTip(i, "\n".join(tips))
        self.refresh()                                   # DSD bypasses the DSP: the switches, curves and cells follow

    def save_backup(self):
        """The state as connected, with the preset slots once all are read, as a copy in the backups folder."""
        if self.taken is None or any(n not in self.session.slots for n in setupfile.SLOTS):
            return
        (state, model), self.taken = self.taken, None
        try:
            text = setupfile.write(state, self.session.slots, model, self.session.revision())
            backup.keep(self.backups, model, text)
        except (OSError, ValueError) as e:
            self.note("Backup not saved: %s" % e, theme.WARN)

    def warn_untested(self):
        """A model Commander has not been tested with: say so before anything is done, once per run. Quit closes
        Commander."""
        model = self.session.model
        if (self.simulated or not self.session.ready() or model in self.warned
                or not untested.due(self.settings, model)):
            return
        self.warned.add(model)
        box = untested.UntestedBox(self, model)
        self.ask(box)
        if box.keep.isChecked():
            self.settings.setValue(untested.key(model), __version__)
        if box.quitting:
            self.close()

    def heard(self):
        """The input the device takes, as shown, and the status of that input when it is SPDIF. With Auto the input
        is the one the device follows: SPDIF before USB."""
        st = self.session.device_status
        source = self.session.state.get((P.OUTPUTS[st.output][1], P.SOURCE))
        if source == P.INPUTS.index("Auto"):
            name = {"coax": "SPDIF coax", "optical": "Optical"}.get(st.clock, "USB")
            return "%s (Auto)" % name, {"coax": st.coax, "optical": st.optical}.get(st.clock)
        return (P.INPUTS[source] if source in range(len(P.INPUTS)) else ""), {1: st.coax, 2: st.optical}.get(source)

    def live_rate(self):
        """The rate the device runs at, or None where it does not apply: no device, DSD (no DSP), or nothing on
        the SPDIF input. Of the ADI-2 Pro and ADI-2/4 Pro: Sample Rate as the device reports it (12/16)."""
        st = self.session.device_status
        if self.session.ready() and self.model.eq_only:
            index = self.session.state.get(P.SAMPLE_RATE)
            return P.SAMPLE_RATES[index] if index in range(len(P.SAMPLE_RATES)) else None
        if not self.session.ready() or st is None or st.dsd:
            return None
        spdif = self.heard()[1]
        return None if spdif is not None and (not spdif.lock or spdif.non_audio) else st.rate

    def show_signal(self):
        """Beside the connection: the input, then the rate and PCM, or DSD. A chosen SPDIF input without a signal,
        or with non-audio data, says so in amber instead: nothing plays."""
        self.show_live_rate()
        if self.model.eq_only:
            self.show_own_rate()
            return
        self.input_text.show()
        self.one_eq.hide()
        st = self.session.device_status
        known = self.session.ready() and st is not None
        self.signal_info.setVisible(known)
        if not known:
            return
        name, spdif = self.heard()
        self.input_text.setText(name)
        if spdif is not None and (not spdif.lock or spdif.non_audio):
            text, color = ("non-audio" if spdif.lock else "no signal"), theme.WARN
        elif st.dsd:
            # DSD over PCM (DoP) carries 16 DSD bits per sample: 176.4 kHz is DSD64
            text, color = "DSD%d" % (st.rate * 16 // 44100) if st.rate % 44100 == 0 else "DSD", theme.LABEL
        else:
            text, color = "%g kHz PCM" % (st.rate / 1000), theme.LABEL
        self.rate_text.setText(text)
        self.rate_text.setStyleSheet(label_color(color))

    def show_own_rate(self):
        """ADI-2 Pro and ADI-2/4 Pro: beside the connection only the rate; from the rate on which the EQ runs on one
        stereo channel only, a note."""
        rate = self.live_rate()
        self.signal_info.setVisible(rate is not None)
        self.input_text.hide()
        if rate is None:
            return
        self.rate_text.setText("%g kHz" % (rate / 1000))
        self.rate_text.setStyleSheet(label_color(theme.LABEL))
        one = self.model.one_eq_from is not None and rate >= self.model.one_eq_from
        self.one_eq.setVisible(one)
        self.one_eq.setToolTip(ONE_EQ_TIP % (self.model.one_eq_from / 1000, self.model.name) if one else "")

    def show_live_rate(self):
        """The chosen fs in amber when the device runs at another rate; as always when it runs at this one, or when
        that does not apply. In the list the rate it runs at is bold."""
        live, loudness = self.live_rate(), self.loudness_shown()
        if (live, self.graph.fs, loudness) == self.live_shown:
            return
        self.live_shown = (live, self.graph.fs, loudness)
        other = live is not None and live != self.graph.fs
        self.fs_box.set_value_color(theme.WARN if other else None)
        compare = "" if loudness else "\nSum curves at that rate are available for comparison through the legend."
        self.fs_box.setToolTip(FS_TIP + ("\nThe device runs at %g kHz.%s" % (live / 1000, compare) if other else ""))
        bold = QFont(self.fs_box.font())
        bold.setBold(True)
        for i, fs in enumerate(SAMPLE_RATES):
            self.fs_box.setItemData(i, bold if fs == live else None, Qt.FontRole)

    def on_changed(self, keys, origin):
        if origin == "device":
            for k in keys:
                self.marks.start_flash(k)            # changed on the device itself: the cell moves along
            if self.draft is None:                   # in the edit stand the cells are the preset's
                for v in self.band_views + [self.bt_view, self.loudness_view]:
                    v.cancel_edit_if(keys)
        self.refresh()

    def on_operation(self, kind, slot, result):
        """Store or Write is done: say how it went. A preset written from the edit stand leaves it, unless the
        device went away first: then the stand stays as it was, to be written once the device is back."""
        done = {"store": "Stored in Preset %d", "write": "Stored Preset %d"}[kind] % slot
        if result is None:
            self.note("Not done: the device was disconnected (Preset %d)" % slot, theme.WARN)
        elif result:
            self.slot_issues[slot] = result
            self.note("%s, but it reads back otherwise (see the preset)" % done, theme.BAD)
        else:
            self.note(done)
        if kind == "write" and self.draft is not None and self.draft.slot == slot:
            if result is None:
                self.draft.locked = False
            else:
                self.leave_edit()
        self.refresh()

    def on_verified(self, results):
        for key, (sent, actual) in results.items():
            if sent == actual:
                self.marks.mismatch.pop(key, None)
            else:
                self.marks.mismatch[key] = (sent, actual)
        self.refresh()

    # -- actions ------------------------------------------------------------------------------
    def next_tab(self, step):
        """The next output Commander controls; the edit stand stays on its output."""
        if self.draft is None:
            n, i = self.tabs.count(), self.tabs.currentIndex()
            self.tabs.setCurrentIndex(next(j % n for j in range(i + step, i + step * n, step)
                                           if self.tabs.isTabEnabled(j % n)))

    def set_output(self, i):
        self.output = P.OUTPUTS[i]
        for m in self.band_models:
            m.set_output(self.output)
        self.bt_model.set_output(self.output)
        self.loudness_model.set_output(self.output)
        self.output_panel.set_output(self.output)
        self.refresh()

    def tab_to(self, view, direction):
        """Tab order: the whole left table, then the right one, then Bass/Treble, then Loudness, then around
        again; row by row, Type -> Freq -> Gain -> Q. Fields that cannot be edited are skipped."""
        views = [v for v in self.band_views + [self.bt_view, self.loudness_view] if v.isVisible()]
        chain = [(vi, r, c) for vi, v in enumerate(views)
                 for r in range(v.model().rowCount()) for c in range(v.model().columnCount())
                 if v.model_.editable(v.model().cell(v.model().index(r, c)))]
        if not chain or view not in views:
            return
        idx = view.currentIndex()
        here = (views.index(view), idx.row(), idx.column())
        if direction > 0:
            nxt = next((p for p in chain if p > here), chain[0])
        else:
            nxt = next((p for p in reversed(chain) if p < here), chain[-1])
        v = views[nxt[0]]
        v.setFocus()
        v.setCurrentIndex(v.model().index(nxt[1], nxt[2]))

    def walk_on(self, view, direction, column):
        """Alt+up/down past the first or last row: carry on in the table above or below, in the cell straight
        above or below; the top and bottom of the stack stop the cursor. The tables line up on the right (Bass/
        Treble and Loudness have no Type column); from Type the cursor lands in Hz."""
        views = [v for v in self.band_views + [self.bt_view, self.loudness_view] if v.isVisible()]
        i = views.index(view) + direction
        if not 0 <= i < len(views):
            return
        v = views[i]
        column = max(0, column + v.model().columnCount() - view.model().columnCount())
        v.setFocus()
        v.setCurrentIndex(v.model().index(0 if direction > 0 else v.model().rowCount() - 1, column))

    def dual_action(self, side):
        """Dual EQ in one click. With Dual EQ on, 'Share L > R' or 'Share R > L' makes that channel's EQ the one for
        both (Dual EQ off). With Dual EQ off, 'Split L <> R' (in the place of Share L > R) gives each channel its own
        EQ, both starting from the shared one; nothing is lost."""
        out, eq = self.output[1], self.eq()
        if not eq.ready() or not self.editable():
            return
        if eq.dual(out):
            eq.set_dual(out, False, keep=("left", "right")[side])
        else:
            eq.set_dual(out, True)

    def output_name(self):
        return self.model.outputs[P.OUTPUTS.index(self.output)]

    def save_dialog(self):
        what = "Preset %d" % self.draft.slot if self.draft is not None else self.output_name()
        name = "%s %s %s.txt" % (self.model.name.replace("/", "-"), what.replace("·", "-").replace("/", "-"),
                                 datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
        path, kind = QFileDialog.getSaveFileName(self, "Save EQ - %s" % what, os.path.join(self.folder, name),
                                                 ";;".join((APO_FILES, REMOTE_FILES)))
        if path and kind == REMOTE_FILES and not path.lower().endswith(REMOTE_SUFFIX):
            path = (path[:-4] if path.lower().endswith(".txt") else path) + REMOTE_SUFFIX
        if path:
            self.save_file(path)

    def save_file(self, path):
        """The EQ of this output, or the preset being edited: as a preset file of ADI-2 Remote when path ends in its
        suffix, named as the preset being edited or else as the file; otherwise as an Equalizer APO file, at the
        sample rate of the graph."""
        self.folder = os.path.dirname(path)
        try:
            if path.lower().endswith(REMOTE_SUFFIX):
                name = (self.draft.name if self.draft is not None else None) or R.name_of(
                    os.path.splitext(os.path.basename(path))[0]) or R.name_of(self.output_name())
                R.save(path, R.write(self.eq().state, self.output[1], name, self.model, self.session.revision()))
            else:
                preset = (self.draft.slot, self.draft.name) if self.draft is not None else None
                E.save(path, E.write(self.eq().state, self.output[1], self.graph.fs, preset=preset,
                                     model=self.model))
        except (OSError, ValueError) as e:
            self.note("Not saved: %s" % e, theme.WARN)
            return
        self.note("Saved %s" % os.path.basename(path))

    def load_dialog(self):
        what = "Preset %d" % self.draft.slot if self.draft is not None else self.output_name()
        path, _ = QFileDialog.getOpenFileName(self, "Load filters - %s" % what, self.folder,
                                              "Filter files and curves (*.txt *.csv);;All files (*)")
        if path:
            self.load_file(path)

    def load_file(self, path):
        """Read a filter file or a curve and write it to this output, or to the preset being edited, after the user
        has chosen in LoadDialog, and only on OK."""
        self.folder = os.path.dirname(path)
        out, eq = self.output[1], self.eq()
        if not eq.ready() or not self.editable():
            self.note("Not loaded: the device is not connected", theme.WARN)
            return
        name = os.path.basename(path)
        try:
            source = read_file(path, self.graph.fs)
        except OSError as e:
            self.note("Not loaded: %s" % e, theme.WARN)
            return
        if source is None:
            self.note("Not loaded: %s is not a filter file or a curve" % name, theme.WARN)
            return
        preset = (self.draft.slot, self.draft.name) if self.draft is not None else None
        dialog = LoadDialog(source, path, eq, out, self.live_rate(), self.graph.fs, self, preset, self.output_name())
        try:
            if not self.ask(dialog):
                self.note("Load cancelled")
                return
            name = os.path.basename(dialog.path)          # another file may have been dropped on the dialog
            if dialog.unchanged:
                self.note("%s: %s" % ("Already in the preset" if preset else "Already on the device", name))
                return
            if not eq.ready():                           # the device may go while the question is open
                self.note("Not loaded: the device is not connected", theme.WARN)
                return
            try:
                I.apply(eq, dialog.values)
            except ValueError as e:                      # e.g. Dual EQ switched on the device meanwhile
                self.note("Not fully loaded: %s" % e, theme.WARN)
                return
            self.note("Loaded %s" % name)
        finally:
            dialog.setParent(None)                       # no longer the window's: gone with its last reference


    def dragEnterEvent(self, e):
        if self.eq().ready() and self.editable() and dropped_file(e.mimeData()):
            e.acceptProposedAction()

    def dropEvent(self, e):
        path = dropped_file(e.mimeData())
        if not path:
            return
        e.acceptProposedAction()
        # after the drop has finished: LoadDialog is modal, and Explorer waits for the drop to return
        QTimer.singleShot(0, lambda: self.load_file(path))

    def ask(self, dialog):
        return dialog.exec() == QDialog.Accepted

    def show_about(self):
        self.ask(AboutDialog(self, QApplication.windowIcon()))

    def note(self, text, color=theme.SECONDARY):
        self.file_note.setText(text.strip())
        self.file_note.setStyleSheet("color: %s;" % color.name())

    def toggle_eq(self, side):
        """EQ Enable of one channel; with Dual EQ off of the one EQ of both, so both switches go together."""
        self.toggle_section((band_address(self.output, side, self.session), P.EQ_ENABLE), self.band_views[side])

    def toggle_bt(self):
        """Bass/Treble Enable: shared by both channels, on the left address."""
        self.toggle_section((self.output[2], P.BT_ENABLE), self.bt_view)

    def toggle_section(self, key, view):
        """Turn a section on or off by its switch. Turning it on is work in it: its table takes the focus, and the
        stage follows. Turning it off gives the focus back to where it was."""
        on = 0
        if self.draft is not None:                       # a title in the edit stand, no switch
            return
        if self.session.writable(key):
            on = 1 - self.session.state[key]
            self.write(key, on, False)
        if on:
            view.take_focus()
        elif self.before_switch:
            self.before_switch.setFocus()

    def toggle_load_bt(self):
        """Load B/T with Preset: whether selecting a preset brings its Bass/Treble too; on the left address."""
        key = (self.output[2], P.LOAD_BT)
        if self.draft is None and self.session.writable(key):
            self.write(key, 1 - self.session.state[key], False)

    def select_preset(self, value):
        """Select what this output's EQ is loaded from; selecting the same preset again loads it again."""
        self.slot_issues.pop(value - 1, None)            # a next action on the row: its mark goes
        self.write((self.output[2], P.EQ_PRESET_SELECT), value, False)

    def store_preset(self, slot):
        self.slot_issues.pop(slot, None)
        try:
            self.session.store(self.output[1], slot)
        except ValueError as e:
            self.note("Not stored: %s" % e, theme.WARN)
            return
        self.note("Storing the EQ of %s in Preset %d …" % (self.output[0], slot))
        self.refresh()

    # -- a preset's preview ------------------------------------------------------------------------
    def previewable(self, row):
        """A slot's row or Clear that can show its preview now: not while it cannot be clicked."""
        return row.previewable and row.isEnabled() and not row.edited

    def open_preview(self, value):
        """A slot's row or Clear came under the mouse: its preview, beside it."""
        row = self.presets.rows[value]
        if row is self.preview_row or self.draft is not None or not self.previewable(row):
            return
        self.preview_row = row
        self.presets.peek(value)
        self.refresh_preview()
        self.place_preview()
        self.preview.show()
        self.preview.raise_()
        self.peek.cover(self.preview.page(), row)

    def close_preview(self):
        if self.preview_row is None:
            return
        self.preview_row = None
        self.preview.hide()
        self.peek.uncover()
        self.presets.peek(None)

    def from_preview(self, act, value):
        """An action in the preview: done with it."""
        self.close_preview()
        act(value)

    def refresh_preview(self):
        row = self.preview_row
        if row is None:
            return
        if self.draft is not None or not self.previewable(row) or not self.presets_area.isVisible():
            self.close_preview()
            return
        s, (_, _, left, _), name = self.session.state, self.output, self.output_name()
        others = [o for o, (_, out, l, _) in zip(self.model.outputs, P.OUTPUTS)
                  if l != left and self.session.controls(out) and s.get((l, P.EQ_PRESET_SELECT)) == row.value]
        self.preview.show_preset(row.value, self.session.slots.get(row.slot), name, s.get((left, P.LOAD_BT)) == 1,
                                 s.get((left, P.EQ_PRESET_SELECT)) == row.value, self.graph.fs, others)

    def place_preview(self):
        """Just past the longest name in the panel, and past the tags of its own row, which stay in sight; the rest of
        the panel lies under it, the graph's zone too where it reaches that far. An edge of the tab runs on as the
        preview's, never nearly: its lower edge, so that the row of its actions lies level with the row; where the
        preview would then rise above the graph's zone, its upper edge."""
        root, row, preview = self.centralWidget(), self.preview_row, self.preview
        preview.resize(preview.sizeHint())
        zone = QRect(self.display.mapTo(root, QPoint(0, 0)), self.display.size())
        names = max(r.mapTo(root, QPoint(r.text_end(r is row), 0)).x() for r in self.presets.rows.values())
        level = row.mapTo(root, QPoint(0, row.height())).y() + RISE - preview.height()
        top = level if level >= zone.top() + PREVIEW_INSET else row.mapTo(root, QPoint(0, 0)).y() - RISE
        at = QPoint(min(names + PREVIEW_GAP, zone.left() + PREVIEW_INSET), top)
        if preview.pos() != at:
            preview.move(at)

    def follow_preview(self, pos):
        """The mouse at pos (on the screen): on another such row, its preview; on the row, the preview or between
        them, this one stays; elsewhere it closes."""
        def rect(w):
            return QRect(w.mapToGlobal(QPoint(0, 0)), w.size())

        shown, page = rect(self.presets_area.viewport()), rect(self.preview)
        if page.contains(pos):                           # over rows too: the preview lies over them
            self.place_preview()
            return
        for row in self.presets.rows.values():
            if self.previewable(row) and row.isVisible() and rect(row).contains(pos) and shown.contains(pos):
                if row is not self.preview_row:
                    self.open_preview(row.value)
                break
        row = self.preview_row
        if row is None:
            return
        page, tab = rect(self.preview), rect(row)
        beside = QRect(QPoint(tab.left(), tab.top() - RISE), QPoint(page.left(), tab.bottom() + RISE))
        gap = QRect(QPoint(shown.right(), page.top()), QPoint(page.left(), page.bottom()))     # when it is beyond
        if any(r.contains(pos) for r in (beside, gap)):
            self.place_preview()                         # the row moves when the panel scrolls
        else:
            self.close_preview()

    # -- the edit stand ---------------------------------------------------------------------------
    def eq(self):
        """What the tables, the graph, Save and Load work on: the preset being edited, or else the output's EQ."""
        return self.draft if self.draft is not None else self.session

    def editable(self):
        """False while the preset being edited is being written."""
        return self.draft is None or not self.draft.locked

    def edit_preset(self, slot):
        """Open the edit stand on preset slot n, as it was read last."""
        if not self.session.ready() or self.session.operating() or self.draft is not None:
            return
        if slot not in self.session.slots:
            self.note("Not yet read: Preset %d" % slot, theme.WARN)
            return
        self.slot_issues.pop(slot, None)                 # a next action on the row: its mark goes
        views = self.band_views + [self.bt_view]
        self.before_edit = ([(v, v.currentIndex().row(), v.currentIndex().column(), v.chosen) for v in views],
                            self.loudness_shown())
        self.draft = Draft(slot, self.session.slots[slot], self.session.state, self.output)
        self.draft.on_changed.append(lambda keys, origin: self.refresh())
        self.show_eq(self.draft, self.draft_marks)
        self.show_stage(loudness=False)
        for v in views:                                  # nothing chosen: no link with the work before
            v.setCurrentIndex(QModelIndex())
            v.chosen = False
            v.viewport().update()
        self.graph.current = None
        if QApplication.focusWidget() is not None:
            QApplication.focusWidget().clearFocus()
        self.preset_name.setText(self.draft.name)
        row = self.presets.rows[slot + 1]
        self.presets_area.ensureWidgetVisible(row, 0, 0)
        for w in self.under_veil():
            w.setEnabled(False)
        self.refresh()
        self.scrim.cover([self.display, self.sound], row)

    def finish_edit(self, ok):
        """OK: write the preset, when changed, and leave once the device has it. Cancel: leave."""
        d = self.draft
        if d is None or d.locked:
            return
        if ok:
            if not d.changed():                          # OK is disabled then
                return
            try:
                self.session.write_slot(d.slot, d.content())
            except ValueError as e:
                self.note("Not stored: %s" % e, theme.WARN)
                return
            d.locked = True                              # the row says storing… in the place of OK
            self.refresh()
            return
        self.note("Edit of Preset %d cancelled" % d.slot)
        self.leave_edit()

    def leave_edit(self):
        """Back to the output's EQ, where the work was before: the chosen cell and the stage."""
        self.draft = None
        self.scrim.uncover()
        for w in self.under_veil():
            w.setEnabled(True)
        self.show_eq(self.session, self.marks)
        self.refresh()
        cells, loudness = self.before_edit
        for v, row, column, chosen in cells:
            v.setCurrentIndex(v.model().index(row, column))
            v.chosen = chosen
            v.viewport().update()
        self.graph.current = None
        chosen = next((v for v, *_, c in cells if c), None)
        if chosen is not None:
            self.on_current(self.band_views.index(chosen) if chosen in self.band_views else None,
                            chosen.currentIndex())
        self.show_stage(loudness)

    def under_veil(self):
        """What the edit stand puts out of reach, besides the other presets' rows (the panel's own)."""
        return [self.tabs, self.input_tab, self.output_tab, self.presets_tab, self.input_area, self.output_area]

    def show_eq(self, source, marks):
        """The tables and the graph on the output's EQ (the session) or on the preset being edited (a Draft)."""
        for m in self.band_models + [self.bt_model]:
            m.session, m.marks = source, marks
        for d in self.band_delegates + [self.bt_delegate]:
            d.marks = marks
        self.graph.session = source

    def rename_draft(self, text):
        if self.draft is not None and not self.draft.locked:
            self.draft.set_name(text)

    def restore_name(self):
        """Escape in the name: the name the preset has."""
        if self.draft is not None and not self.draft.locked:
            self.draft.set_name(self.draft.base["name"].strip())
            self.preset_name.setText(self.draft.name)

    def edit_warning(self):
        """What OK changes beyond the preset, a line each; '' when nothing: the preset's name in its row is amber
        when there is something, with this as its tooltip. Nothing while the preset is unchanged: OK is disabled
        then."""
        d, session, live = self.draft, self.session, self.session.state
        if not session.ready() or session.operating() or not d.changed():
            return ""
        lines = []
        chosen = [name for name, (_, out, left, _) in zip(self.model.outputs, P.OUTPUTS)
                  if session.controls(out) and live.get((left, P.EQ_PRESET_SELECT)) == d.slot + 1]
        if chosen:
            lines.append("Selected on %s: OK loads it there" % " and ".join(chosen))
        if session.slots.get(d.slot) not in (None, d.stored):
            lines.append("Preset %d was changed on the device meanwhile: OK writes this over it" % d.slot)
        return "\n".join(lines)

    def toggle_loudness(self):
        """Loudness Enable: on the output address, for both channels."""
        self.toggle_section((self.output[1], P.LOUDNESS_ENABLE), self.loudness_view)

    def on_current(self, side, idx):
        """The table's current row is drawn highlighted in the graph; a left and a right point on the same
        spot go to the channel last worked on."""
        if not idx.isValid():
            return
        self.show_stage(loudness=False)
        if side is None:
            self.graph.current = (self.output[2], "BT"[idx.row()])
        else:
            self.graph.current = (band_address(self.output, side, self.eq()), str(idx.row() + 1))
            self.graph.prefer_side = side
        self.graph.update_from(self.output)

    def on_loudness_current(self, idx):
        if idx.isValid():
            self.show_stage(loudness=True)
            m = self.loudness_model
            self.loudness_graph.set_current(m.cell(m.index(idx.row(), 1)).key)   # the row's point, on any column

    def loudness_shown(self):
        return self.stage.currentWidget() is self.loudness_graph

    def show_stage(self, loudness):
        """The stage follows the table one works in: the Loudness graph for the Loudness table, else the response
        graph. At once."""
        if loudness == self.loudness_shown():
            return
        self.stage.setCurrentWidget(self.loudness_graph if loudness else self.graph)
        self.graph_head.set_legend(self.loudness_graph.legend if loudness else self.legend)
        self.refresh()

    def set_fs(self, *_):
        self.graph.fs = self.fs_box.currentData()
        self.refresh()

    def on_focus(self, old, new):
        if new is None or new.window() is not self:
            return
        views = self.band_views + [self.bt_view]
        if isinstance(new, Switch):
            # a switch passes the focus on; turned off, back to where it was: from an editor, which closes, its table
            here = old is not None and old.window() is self
            self.before_switch = here and next((v for v in views + [self.loudness_view] if v.isAncestorOf(old)), old)
            return
        if new in views + [self.loudness_view]:
            for v in views + [self.loudness_view]:      # the chosen row: shown in its table without focus too
                v.chosen = v is new
                v.viewport().update()
        if new in views:
            self.on_current((0, 1, None)[views.index(new)], new.currentIndex())
        elif new is self.loudness_view:
            self.on_loudness_current(new.currentIndex())

    def select_cell(self, key):
        """A point in a graph was taken: its row in the table becomes current, on the frequency (a Loudness point:
        on its gain). With Dual EQ off the point is in both tables: the one last worked on."""
        first = self.graph.prefer_side
        for v in [self.band_views[first], self.band_views[1 - first], self.bt_view, self.loudness_view]:
            m = v.model()
            for r in range(m.rowCount()):
                for c in range(m.columnCount()):
                    cell = m.cell(m.index(r, c))
                    if cell.key == key and v.isVisible():
                        v.setFocus()
                        v.setCurrentIndex(m.index(r, c))
                        return

    def show_panel_lines(self):
        """A line before each open panel that has an open panel before it."""
        areas = (self.input_area, self.output_area, self.presets_area)
        for n, line in enumerate(self.panel_lines):
            line.setVisible(not areas[n + 1].isHidden() and any(not a.isHidden() for a in areas[:n + 1]))

    def write(self, key, value, adjusted):
        eq = self.eq()
        if not eq.writable(key):
            return
        if adjusted:                                     # the cell shows what is really sent
            (self.marks if self.draft is None else self.draft_marks).start_flash(key)
        eq.set(key, value)

    def refresh_presets(self):
        """The presets panel, and the source line as its selected row."""
        s, (_, out, left, _), ready = self.session.state, self.output, self.session.ready()
        d = self.draft
        editing = None if d is None else (d.slot, d.name, ready and not d.locked and d.changed(), self.edit_warning(),
                                          "Nothing to write: the preset is unchanged" if not d.changed() else
                                          "" if ready else "OK waits for the device: it is not connected")
        tags = {o: tag for tag, (_, o, _, _) in zip(self.model.tags, P.OUTPUTS) if o in self.model.controlled}
        self.presets.refresh(s, (self.output_name(),) + self.output[1:], self.session.slots, ready,
                             self.session.operation(), self.slot_issues, editing, tags)
        self.source.copy(self.presets.rows.get(s.get((left, P.EQ_PRESET_SELECT))) if ready and not editing else None,
                         bool(self.session.stale(out)))
        self.refresh_preview()

    def refresh_slots(self):
        """The slots show only in the presets panel."""
        self.refresh_presets()

    def refresh_edit(self):
        """The head and the foot of the column in the edit stand."""
        d = self.draft
        editing = d is not None
        self.eq_title.setText("PRESET" if editing else "EQ")
        for w in (self.preset_number, self.preset_name):
            w.setVisible(editing)
        self.loudness_view.setVisible(not editing)       # no part of a preset
        if not editing:
            return
        self.preset_number.setText(str(d.slot))
        self.preset_name.setEnabled(not d.locked)
        if self.preset_name.text() != d.name:
            self.preset_name.setText(d.name)

    def refresh(self):
        eq, (_, out, left, _) = self.eq(), self.output
        s, ready, editing = eq.state, eq.ready(), self.draft is not None
        dual = not ready or s.get((out, P.DUAL_EQ)) == 1
        eq_on = [ready and s.get((band_address(self.output, side, eq), P.EQ_ENABLE)) == 1 for side in (0, 1)]
        bt_on = ready and s.get((left, P.BT_ENABLE)) == 1
        loudness_on = ready and s.get((out, P.LOUDNESS_ENABLE)) == 1
        bypassed = ready and eq.bypassed()
        for side, name in enumerate(("left", "right")):
            switch = self.eq_switches[side]
            switch.name = EQ_OWN[side] if dual else EQ_SHARED[side]           # its own channel first
            switch.color = side_color(side, dual)
            if editing:
                switch.show_title("EQ of the %s channel in this preset" % name if dual else
                                  "Dual EQ off: one EQ for both channels in this preset")
            else:
                switch.show_state(eq_on[side], ready, switch_tip("EQ of the %s channel" % name, eq_on[side]) if dual
                                  else "Dual EQ off: one EQ for both channels\n" + switch_tip("EQ", eq_on[side]),
                                  bypassed)
            self.band_delegates[side].color = side_color(side, dual)
            act = self.dual_actions[side]
            act.setEnabled(ready and self.editable())
            act.setText(SHARE[side] if dual else SPLIT)
            act.setVisible(dual or side == 0)
            act.setToolTip("Apply the %s channel's EQ to both channels (Dual EQ off).\n"
                           "This replaces the %s channel's EQ." % (name, ("right", "left")[side]) if dual else
                           "Make each channel's EQ independent (Dual EQ on).\nBoth start from this EQ.")
        self.save_action.setEnabled(ready)
        self.load_action.setEnabled(ready and self.editable())
        live = self.session.ready()
        load_bt = live and self.session.state.get((left, P.LOAD_BT)) == 1
        if editing:
            self.bt_switch.show_title(BT_IN_PRESET)
        else:
            self.bt_switch.show_state(bt_on, ready, switch_tip("Bass/Treble, both channels", bt_on) + "\n" + (
                "Loaded with a preset: Load Bass/Treble with preset is on." if load_bt else
                "Not loaded with a preset: Load Bass/Treble with preset is off."), bypassed)
        self.loudness_switch.show_state(loudness_on, ready, switch_tip("Loudness, both channels", loudness_on),
                                        bypassed)
        self.load_bt.show_state(load_bt, live and not editing, "Load Bass/Treble with preset: %s\n"
                                "On: selecting a preset brings its Bass/Treble too, and changing Bass/Treble on a\n"
                                "preset makes it Temp.%s" % ("on" if load_bt else "off", "" if self.model.eq_only else
                                                             " Switching it on switches Bass/Treble off on Phones and"
                                                             " IEM\n(the device does so)."))
        self.refresh_presets()
        self.refresh_edit()
        if not self.model.eq_only:                       # else closed, and their names are those of the DAC FS
            self.input_panel.refresh()
            self.output_panel.refresh()
        for m in self.band_models + [self.bt_model, self.loudness_model]:
            m.refresh()
        rate = self.live_rate()                          # compared: the rate the device runs at, when it is another
        self.graph.fs_compare = rate if rate != self.graph.fs else None
        self.graph.update_from(self.output)
        self.loudness_graph.update_from(s if ready else {}, out, fs=self.graph.fs, bypassed=bypassed,
                                        draw=self.loudness_shown())     # drawn when it takes the stage
        self.legend.refresh()
        self.graph_head.legend.setVisible(ready)
        self.graph_note.setText("No %s at %g kHz" % ("Loudness" if self.loudness_shown() else "Bass/Treble",
                                                     self.graph.fs / 1000)
                                if ready and self.graph.fs >= self.model.no_bt_from else "")
        self.graph_head.refit()                          # the legend and the note can change width
        self.show_signal()
