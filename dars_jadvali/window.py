"""Asosiy oyna: Bugun, Hafta jadvali, Vazifalar, Sozlamalar (yuqori panelli ixcham joylashuv)."""
import json
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

from PySide6.QtCore import QDate, QDateTime, QRectF, QSize, Qt, QTime, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QImage, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QColorDialog, QComboBox,
                               QDateEdit, QDateTimeEdit, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame,
                               QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMenu, QMessageBox,
                               QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QSpinBox, QStackedWidget,
                               QTableWidget, QTableWidgetItem, QTimeEdit, QToolButton, QVBoxLayout, QWidget)

from uzkit import app as appmod
from uzkit.i18n import language, register, tr
from uzkit.paths import resource
from uzkit.widgets import Card, ask, danger_button, error, header, info, open_path, primary_button, warn
from uzkit.window import BaseMainWindow

from . import schedule as sc
from .grid import DAY_KEYS, GridModel, WeekGrid, paint_week
from .strings import STRINGS
from .ui_extra import (Tray, accent, app_data_dir, autostart_command, icon, is_autostart, is_demo, mix, pal,
                       set_autostart, soft)

register(STRINGS)

SLUG = "dars-jadvali"
AUTOSTART_NAME = "BahtiyorSoft.DarsJadvali"
PRIO_COLORS = {"low": "#2f9e44", "medium": "#e67700", "high": "#e03131"}


def now() -> datetime:
    """Skrinshot rejimida 'hozir' namunaviy vaqtga o'rnatiladi (jadval jonli ko'rinishi uchun)."""
    if is_demo():
        d = date.today()
        d = d - timedelta(days=d.weekday()) + timedelta(days=min(d.weekday(), 3))
        return datetime.combine(d, time(10, 42))
    return datetime.now()


def fmt_left(minutes: float) -> str:
    d, h, m = sc.humanize_minutes(minutes)
    if d:
        return tr("left_dh", d=d, h=h)
    if h:
        return tr("left_hm", h=h, m=m)
    return tr("left_m", m=m)


def week_label(store, monday: date) -> str:
    n = sc.week_number(store.semester_start, monday)
    return tr("week_n", n=n, p=tr("wk_" + sc.parity(n)))


def icon_button(name, tip, text=""):
    b = QPushButton(text)
    b.setIcon(icon(name, pal()["text"]))
    b.setIconSize(QSize(18, 18))
    b.setToolTip(tip)
    b.setAccessibleName(tip)
    if not text:
        b.setFixedWidth(40)
    return b


# =========================================================================== dialoglar
class LessonDialog(QDialog):
    def __init__(self, parent, store: sc.Store, lesson=None, day=0, pair=1):
        super().__init__(parent)
        self.store = store
        self.lesson = dict(lesson) if lesson else {}
        self.setWindowTitle(tr("edit_lesson") if lesson else tr("add_lesson"))
        self.setMinimumWidth(460)
        l = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(9)
        self.subject = QComboBox()
        self.subject.setEditable(True)
        self.subject.addItems(store.subjects())
        self.subject.setCurrentText(self.lesson.get("subject", ""))
        self.subject.lineEdit().setPlaceholderText(tr("subject_ph"))
        self.type = QComboBox()
        for t in sc.LESSON_TYPES:
            self.type.addItem(tr("type_" + t), t)
        self.group = QLineEdit(self.lesson.get("group", ""))
        self.group.setPlaceholderText("KI-21, DI-22")
        self.room = QLineEdit(self.lesson.get("room", ""))
        self.room.setPlaceholderText("A-305")
        self.day = QComboBox()
        for d in range(7):
            self.day.addItem(tr(DAY_KEYS[d] + "_full"), d)
        self.pair = QComboBox()
        for i, p in enumerate(store.pairs, 1):
            self.pair.addItem(f"{i}  ({p['start']}–{p['end']})", i)
        self.week = QComboBox()
        for w in sc.WEEK_MODES:
            self.week.addItem(tr("wkm_" + w), w)
        self.color_btn = QPushButton()
        self.color_btn.clicked.connect(self._pick_color)
        self.auto_color = QPushButton(tr("auto_color"))
        self.auto_color.clicked.connect(lambda: self._set_color(""))
        crow = QHBoxLayout()
        crow.addWidget(self.color_btn, 1)
        crow.addWidget(self.auto_color)
        self.notes = QPlainTextEdit(self.lesson.get("notes", ""))
        self.notes.setFixedHeight(56)
        form.addRow(tr("subject"), self.subject)
        form.addRow(tr("ltype"), self.type)
        form.addRow(tr("groups"), self.group)
        form.addRow(tr("room"), self.room)
        form.addRow(tr("day"), self.day)
        form.addRow(tr("pair"), self.pair)
        form.addRow(tr("week_mode"), self.week)
        form.addRow(tr("color"), crow)
        form.addRow(tr("notes"), self.notes)
        l.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("save"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("cancel"))
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        l.addWidget(bb)
        self.type.setCurrentIndex(max(0, self.type.findData(self.lesson.get("type", "lecture"))))
        self.day.setCurrentIndex(max(0, self.day.findData(self.lesson.get("day", day))))
        self.pair.setCurrentIndex(max(0, self.pair.findData(int(self.lesson.get("pair", pair)))))
        self.week.setCurrentIndex(max(0, self.week.findData(self.lesson.get("week", "all"))))
        self._set_color(self.lesson.get("color", ""))
        self.subject.currentTextChanged.connect(lambda *_: self._set_color(self._color))

    def _set_color(self, c):
        self._color = c
        shown = c or self.store.color_of(self.subject.currentText() or "?")
        self.color_btn.setText(tr("color_auto") if not c else c)
        self.color_btn.setStyleSheet(f"QPushButton {{ background: {shown}; color: white; font-weight: 600; }}")

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(self._color or self.store.color_of(self.subject.currentText() or "?")), self)
        if c.isValid():
            self._set_color(c.name())

    def _ok(self):
        if not self.subject.currentText().strip():
            warn(self, tr("need_subject"))
            return
        self.accept()

    def values(self) -> dict:
        v = dict(self.lesson)
        v.update({"subject": self.subject.currentText().strip(), "type": self.type.currentData(),
                  "group": self.group.text().strip(), "room": self.room.text().strip(),
                  "day": self.day.currentData(), "pair": self.pair.currentData(), "week": self.week.currentData(),
                  "color": self._color, "notes": self.notes.toPlainText().strip()})
        return v


class DeadlineDialog(QDialog):
    def __init__(self, parent, store: sc.Store, dl=None):
        super().__init__(parent)
        self.dl = dict(dl) if dl else {}
        self.setWindowTitle(tr("edit_task") if dl else tr("add_task"))
        self.setMinimumWidth(440)
        l = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(9)
        self.title = QLineEdit(self.dl.get("title", ""))
        self.title.setPlaceholderText(tr("task_ph"))
        self.due = QDateTimeEdit()
        self.due.setCalendarPopup(True)
        self.due.setDisplayFormat("dd.MM.yyyy  HH:mm")
        if self.dl.get("due"):
            self.due.setDateTime(QDateTime.fromString(self.dl["due"], "yyyy-MM-ddTHH:mm"))
        else:
            self.due.setDateTime(QDateTime(QDate.currentDate().addDays(1), QTime(18, 0)))
        self.prio = QComboBox()
        for p in sc.PRIORITIES:
            self.prio.addItem(tr("prio_" + p), p)
        self.prio.setCurrentIndex(max(0, self.prio.findData(self.dl.get("priority", "medium"))))
        self.subject = QComboBox()
        self.subject.setEditable(True)
        self.subject.addItems([""] + store.subjects())
        self.subject.setCurrentText(self.dl.get("subject", ""))
        self.notes = QPlainTextEdit(self.dl.get("notes", ""))
        self.notes.setFixedHeight(64)
        form.addRow(tr("task"), self.title)
        form.addRow(tr("due"), self.due)
        form.addRow(tr("priority"), self.prio)
        form.addRow(tr("subject"), self.subject)
        form.addRow(tr("notes"), self.notes)
        l.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("save"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("cancel"))
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        l.addWidget(bb)

    def _ok(self):
        if not self.title.text().strip():
            warn(self, tr("need_task"))
            return
        self.accept()

    def values(self) -> dict:
        v = dict(self.dl)
        v.update({"title": self.title.text().strip(),
                  "due": self.due.dateTime().toString("yyyy-MM-ddTHH:mm"),
                  "priority": self.prio.currentData(), "subject": self.subject.currentText().strip(),
                  "notes": self.notes.toPlainText().strip(), "done": bool(self.dl.get("done"))})
        return v


# =========================================================================== Bugun
class LessonRow(QFrame):
    def __init__(self, l, st, en, state, col):
        super().__init__()
        self.setObjectName("LessonRow")
        c = pal()
        bg = mix(col, c["surface"], 0.88 if state != "past" else 0.95).name()
        self.setStyleSheet(f"QFrame#LessonRow {{ background: {bg}; border-radius: 10px; border-left: 5px solid {col}; }}"
                           f"QFrame#LessonRow QLabel {{ background: transparent; }}")
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 10, 14, 10)
        h.setSpacing(16)
        t = QLabel(f"{st:%H:%M}\n{en:%H:%M}")
        t.setStyleSheet(f"font-size: 11pt; font-weight: 600; color: {c['muted'] if state == 'past' else c['text']};")
        t.setFixedWidth(54)
        h.addWidget(t)
        mid = QVBoxLayout()
        mid.setSpacing(2)
        s = QLabel(l["subject"])
        s.setStyleSheet(f"font-size: 12pt; font-weight: 700; color: {mix(col, c['text'], 0.55).name()};")
        s.setWordWrap(True)
        mid.addWidget(s)
        tag = tr("type_" + l["type"]) + (f"  ·  {tr('wk_' + l['week'])}" if l.get("week", "all") != "all" else "")
        det = "   ".join(x for x in (tag, l.get("room", ""), l.get("group", "")) if x)
        d = QLabel(det)
        d.setObjectName("Muted")
        d.setWordWrap(True)
        mid.addWidget(d)
        h.addLayout(mid, 1)
        if state in ("now", "next"):
            b = QLabel(tr("st_now") if state == "now" else tr("st_next"))
            bc = "#e03131" if state == "now" else col
            b.setStyleSheet(f"background: {bc}; color: white; border-radius: 9px; padding: 3px 10px;"
                            f" font-weight: 700; font-size: 9pt;")
            h.addWidget(b, 0, Qt.AlignVCenter)


class TodayPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QHBoxLayout(self)
        lay.setSpacing(16)
        left = QVBoxLayout()
        left.setSpacing(12)
        self.title = QLabel()
        self.title.setObjectName("Title")
        self.sub = QLabel()
        self.sub.setObjectName("Subtitle")
        left.addWidget(self.title)
        left.addWidget(self.sub)
        self.next_card = QFrame()
        self.next_card.setObjectName("Hero")
        nl = QHBoxLayout(self.next_card)
        nl.setContentsMargins(20, 16, 20, 16)
        col = QVBoxLayout()
        self.next_cap = QLabel()
        self.next_cap.setObjectName("HeroCap")
        self.next_subj = QLabel()
        self.next_subj.setObjectName("HeroTitle")
        self.next_subj.setWordWrap(True)
        self.next_det = QLabel()
        self.next_det.setObjectName("HeroCap")
        self.next_det.setWordWrap(True)
        col.addWidget(self.next_cap)
        col.addWidget(self.next_subj)
        col.addWidget(self.next_det)
        nl.addLayout(col, 1)
        self.countdown = QLabel()
        self.countdown.setObjectName("HeroBig")
        self.countdown.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        nl.addWidget(self.countdown)
        left.addWidget(self.next_card)
        lt = QLabel(tr("today_lessons"))
        lt.setObjectName("SectionTitle")
        left.addWidget(lt)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_host = QWidget()
        self.list_lay = QVBoxLayout(self.list_host)
        self.list_lay.setContentsMargins(0, 0, 6, 0)
        self.list_lay.setSpacing(8)
        self.scroll.setWidget(self.list_host)
        left.addWidget(self.scroll, 1)
        lay.addLayout(left, 3)

        right = Card(tr("tasks_soon"))
        self.tasks_lay = QVBoxLayout()
        self.tasks_lay.setSpacing(6)
        right.add(self.tasks_lay)
        right.lay.addStretch(1)
        qa = QPushButton(tr("add_task_btn"))
        qa.setIcon(icon("plus", pal()["text"]))
        qa.clicked.connect(lambda: win.add_deadline())
        right.add(qa)
        right.setMinimumWidth(250)
        right.setMaximumWidth(360)
        lay.addWidget(right, 2)

    def refresh(self):
        st = self.win.store
        n = now()
        d = n.date()
        self.title.setText(tr("today_title", day=tr(DAY_KEYS[d.weekday()] + "_full"), date=d.strftime("%d.%m.%Y")))
        self.sub.setText(week_label(st, d))
        nx = sc.next_class(st.lessons, st.pairs, n, st.semester_start)
        if nx:
            l, s, e, running = nx
            self.next_cap.setText(tr("now_running") if running else tr("next_class"))
            self.next_subj.setText(l["subject"])
            when = "" if s.date() == d else f"{tr(DAY_KEYS[s.weekday()] + '_full')}, "
            self.next_det.setText(f"{when}{s:%H:%M}–{e:%H:%M}   {tr('type_' + l['type'])}   "
                                  + "   ".join(x for x in (l.get("room", ""), l.get("group", "")) if x))
            mins = (e - n).total_seconds() / 60 if running else (s - n).total_seconds() / 60
            self.countdown.setText((tr("ends_in") if running else tr("starts_in")) + "\n" + fmt_left(mins))
        else:
            self.next_cap.setText(tr("next_class"))
            self.next_subj.setText(tr("no_classes_soon"))
            self.next_det.setText(tr("add_lessons_hint"))
            self.countdown.setText("")
        while self.list_lay.count():
            it = self.list_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        items = sc.lessons_on(st.lessons, d, st.semester_start)
        next_marked = False
        for l in items:
            span = sc.pair_span(st.pairs, int(l["pair"]), d)
            if not span:
                continue
            s, e = span
            if e <= n:
                state = "past"
            elif s <= n:
                state = "now"
            elif not next_marked:
                state = "next"
            else:
                state = ""
            if state in ("now", "next"):
                next_marked = True
            self.list_lay.addWidget(LessonRow(l, s, e, state, st.color_of(l)))
        if not items:
            e = QLabel(tr("no_lessons_today"))
            e.setObjectName("Muted")
            e.setAlignment(Qt.AlignCenter)
            e.setMinimumHeight(120)
            e.setWordWrap(True)
            self.list_lay.addWidget(e)
        self.list_lay.addStretch(1)
        # vazifalar
        while self.tasks_lay.count():
            it = self.tasks_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        soon = [x for x in sc.filter_deadlines(st.deadlines, "active", n)
                if datetime.fromisoformat(x["due"]) <= n + timedelta(days=3)]
        for x in soon[:8]:
            due = datetime.fromisoformat(x["due"])
            left_m = (due - n).total_seconds() / 60
            lab = QLabel()
            lab.setWordWrap(True)
            pc = PRIO_COLORS[x["priority"]]
            when = tr("overdue") if left_m < 0 else fmt_left(left_m)
            lab.setText(f"<span style='color:{pc}; font-size:12pt'>&#9679;</span> <b>{x['title']}</b><br>"
                        f"<span style='color:{pal()['muted']}'>{due:%d.%m %H:%M} · "
                        f"<span style='color:{'#e03131' if left_m < 0 else pal()['muted']}'>{when}</span></span>")
            self.tasks_lay.addWidget(lab)
        if not soon:
            e = QLabel(tr("no_tasks_soon"))
            e.setObjectName("Muted")
            e.setWordWrap(True)
            self.tasks_lay.addWidget(e)


# =========================================================================== Hafta
class WeekPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.monday = sc.monday(now().date())
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.prev = icon_button("up", tr("prev_week"))
        self.prev.setIcon(_rot_icon("up", -90))
        self.next = icon_button("up", tr("next_week"))
        self.next.setIcon(_rot_icon("up", 90))
        self.lbl = QLabel()
        self.lbl.setObjectName("WeekLabel")
        self.today_btn = QPushButton(tr("this_week"))
        self.all_cb = QCheckBox(tr("show_all_weeks"))
        bar.addWidget(self.prev)
        bar.addWidget(self.next)
        bar.addWidget(self.lbl)
        bar.addSpacing(8)
        bar.addWidget(self.today_btn)
        bar.addStretch(1)
        bar.addWidget(self.all_cb)
        self.exp = icon_button("export", tr("export"), tr("export"))
        m = QMenu(self)
        m.addAction(tr("export_pdf"), self.export_pdf)
        m.addAction(tr("export_png"), self.export_png)
        m.addAction(tr("print"), self.print_)
        self.exp.setMenu(m)
        bar.addWidget(self.exp)
        self.add = primary_button(tr("add_lesson_btn"))
        self.add.clicked.connect(lambda: self.win.add_lesson())
        bar.addWidget(self.add)
        lay.addLayout(bar)
        self.grid = WeekGrid()
        lay.addWidget(self.grid, 1)
        hint = QLabel(tr("grid_hint"))
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self.prev.clicked.connect(lambda: self.shift(-7))
        self.next.clicked.connect(lambda: self.shift(7))
        self.today_btn.clicked.connect(self.go_today)
        self.all_cb.toggled.connect(lambda *_: self.refresh())
        self.grid.empty_clicked.connect(lambda d, p: self.win.add_lesson(d, p))
        self.grid.lesson_activated.connect(self.win.edit_lesson)
        self.grid.lesson_menu.connect(self._menu)

    def shift(self, days):
        self.monday += timedelta(days=days)
        self.refresh()

    def go_today(self):
        self.monday = sc.monday(now().date())
        self.refresh()

    def model(self, show_all=None):
        return GridModel(self.win.store, self.monday, self.all_cb.isChecked() if show_all is None else show_all, now())

    def refresh(self):
        st = self.win.store
        end = self.monday + timedelta(days=6)
        self.lbl.setText(f"<b>{week_label(st, self.monday)}</b><br><span style='color:{pal()['muted']};"
                         f" font-size:9pt'>{self.monday:%d.%m} – {end:%d.%m.%Y}</span>")
        self.grid.set_model(self.model())

    def _menu(self, l, gpos):
        m = QMenu(self)
        m.addAction(tr("edit"), lambda: self.win.edit_lesson(l))
        m.addAction(tr("duplicate"), lambda: self.win.duplicate_lesson(l))
        m.addSeparator()
        m.addAction(tr("delete"), lambda: self.win.delete_lesson(l))
        m.exec(gpos)

    # ----- eksport
    def _render_image(self, w=2200, h=1400) -> QImage:
        img = QImage(w, h, QImage.Format_ARGB32)
        img.fill(QColor("#ffffff"))
        p = QPainter(img)
        f = QFont(appmod.META.get("font") or "Segoe UI", 10)
        p.setFont(f)
        p.scale(2, 2)
        self._paint_print(p, QRectF(0, 0, w / 2, h / 2))
        p.end()
        return img

    def _paint_print(self, p, rect):
        from uzkit.theme import PALETTES
        c = dict(PALETTES["light"])
        c.update({"bg": "#ffffff", "surface": "#ffffff", "accent": accent()})
        f = QFont(p.font())
        f.setBold(True)
        f.setPointSizeF(14)
        p.save()
        p.setFont(f)
        p.setPen(QColor("#1c1f26"))
        title = f"{tr('timetable')}   ·   {week_label(self.win.store, self.monday)}"
        if self.all_cb.isChecked():
            title = f"{tr('timetable')}   ·   {tr('all_weeks')}"
        p.drawText(QRectF(rect.left() + 10, rect.top() + 6, rect.width() - 20, 30), Qt.AlignLeft | Qt.AlignVCenter,
                   title)
        p.restore()
        paint_week(p, QRectF(rect.left() + 8, rect.top() + 44, rect.width() - 16, rect.height() - 54),
                   self.model(), c, print_mode=True)

    def export_png(self):
        path, _ = QFileDialog.getSaveFileName(self, tr("export_png"), str(Path.home() / "dars_jadvali.png"),
                                              "PNG (*.png)")
        if not path:
            return
        if self._render_image().save(path):
            self.win.status(tr("saved_to", path=path))
            open_path(path)
        else:
            error(self, tr("export_error"))

    def export_pdf(self):
        path, _ = QFileDialog.getSaveFileName(self, tr("export_pdf"), str(Path.home() / "dars_jadvali.pdf"),
                                              "PDF (*.pdf)")
        if not path:
            return
        try:
            export_pdf(self, path)
            self.win.status(tr("saved_to", path=path))
            open_path(path)
        except Exception as ex:
            appmod.log_exception(ex)
            error(self, tr("export_error"))

    def print_(self):
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        from PySide6.QtGui import QPageLayout
        pr = QPrinter(QPrinter.HighResolution)
        pr.setPageOrientation(QPageLayout.Landscape)
        if QPrintDialog(pr, self).exec():
            self._print_to(pr)

    def _print_to(self, printer):
        p = QPainter(printer)
        r = printer.pageLayout().paintRectPixels(printer.resolution())
        scale = printer.resolution() / 96.0
        p.scale(scale, scale)
        p.setFont(QFont(appmod.META.get("font") or "Segoe UI", 10))
        self._paint_print(p, QRectF(0, 0, r.width() / scale, r.height() / scale))
        p.end()


def export_pdf(page: "WeekPage", path: str):
    from PySide6.QtCore import QMarginsF
    from PySide6.QtGui import QPageLayout, QPageSize
    from PySide6.QtPrintSupport import QPrinter
    pr = QPrinter(QPrinter.HighResolution)
    pr.setOutputFormat(QPrinter.PdfFormat)
    pr.setOutputFileName(path)
    pr.setPageSize(QPageSize(QPageSize.A4))
    pr.setPageOrientation(QPageLayout.Landscape)
    pr.setPageMargins(QMarginsF(10, 10, 10, 10), QPageLayout.Millimeter)
    page._print_to(pr)


def _rot_icon(name, angle):
    from PySide6.QtGui import QPixmap, QTransform
    ic = icon(name, pal()["text"], 18)
    pm = ic.pixmap(36, 36).transformed(QTransform().rotate(angle), Qt.SmoothTransformation)
    return QIcon(pm)


# =========================================================================== Vazifalar
class TasksPage(QWidget):
    MODES = ["active", "overdue", "done", "all"]

    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        qa = QFrame()
        qa.setObjectName("QuickAdd")
        ql = QHBoxLayout(qa)
        ql.setContentsMargins(10, 8, 10, 8)
        ql.setSpacing(8)
        pl = QLabel()
        pl.setPixmap(icon("plus", accent(), 18).pixmap(18, 18))
        ql.addWidget(pl)
        self.q_title = QLineEdit()
        self.q_title.setPlaceholderText(tr("quick_ph"))
        self.q_title.setObjectName("QuickEdit")
        ql.addWidget(self.q_title, 1)
        self.q_due = QDateTimeEdit(QDateTime(QDate.currentDate().addDays(1), QTime(18, 0)))
        self.q_due.setCalendarPopup(True)
        self.q_due.setDisplayFormat("dd.MM.yyyy HH:mm")
        ql.addWidget(self.q_due)
        self.q_prio = QComboBox()
        for p in sc.PRIORITIES:
            self.q_prio.addItem(tr("prio_" + p), p)
        self.q_prio.setCurrentIndex(1)
        ql.addWidget(self.q_prio)
        self.q_add = primary_button(tr("add"))
        ql.addWidget(self.q_add)
        lay.addWidget(qa)
        bar = QHBoxLayout()
        self.filter_btns = QButtonGroup(self)
        for i, m in enumerate(self.MODES):
            b = QPushButton(tr("f_" + m))
            b.setCheckable(True)
            b.setObjectName("Seg")
            self.filter_btns.addButton(b, i)
            bar.addWidget(b)
        self.filter_btns.button(0).setChecked(True)
        bar.addStretch(1)
        self.b_done = icon_button("check", tr("toggle_done"), tr("toggle_done"))
        self.b_edit = icon_button("edit", tr("edit"))
        self.b_del = icon_button("trash", tr("delete"))
        for b in (self.b_done, self.b_edit, self.b_del):
            bar.addWidget(b)
        lay.addLayout(bar)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["", tr("task"), tr("due"), tr("priority"), tr("subject")])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 34)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.Interactive)
        self.table.setColumnWidth(4, 170)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        lay.addWidget(self.table, 1)
        self.empty = QLabel(tr("no_tasks"))
        self.empty.setObjectName("Muted")
        self.empty.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.empty)
        self.q_add.clicked.connect(self.quick_add)
        self.q_title.returnPressed.connect(self.quick_add)
        self.filter_btns.idClicked.connect(lambda *_: self.refresh())
        self.table.doubleClicked.connect(lambda *_: self.edit())
        self.table.cellClicked.connect(self._cell_clicked)
        self.b_done.clicked.connect(self.toggle)
        self.b_edit.clicked.connect(self.edit)
        self.b_del.clicked.connect(self.delete)
        for key, fn in (("Delete", self.delete), ("F2", self.edit), ("Space", self.toggle)):
            sc_ = QShortcut(QKeySequence(key), self.table)
            sc_.setContext(Qt.WidgetShortcut)
            sc_.activated.connect(fn)

    def mode(self):
        return self.MODES[max(0, self.filter_btns.checkedId())]

    def refresh(self):
        st = self.win.store
        n = now()
        rows = sc.filter_deadlines(st.deadlines, self.mode(), n)
        self.table.setRowCount(len(rows))
        c = pal()
        for r, d in enumerate(rows):
            due = datetime.fromisoformat(d["due"])
            state = sc.deadline_state(d, n)
            chk = QTableWidgetItem()
            chk.setData(Qt.UserRole, d["id"])
            chk.setIcon(icon("checkbox" if d["done"] else "square", "#2f9e44" if d["done"] else c["muted"], 18))
            self.table.setItem(r, 0, chk)
            t = QTableWidgetItem(d["title"])
            if d["done"]:
                f = t.font()
                f.setStrikeOut(True)
                t.setFont(f)
                t.setForeground(QColor(c["muted"]))
            if d.get("notes"):
                t.setToolTip(d["notes"])
            self.table.setItem(r, 1, t)
            left = (due - n).total_seconds() / 60
            dtxt = f"{due:%d.%m.%Y %H:%M}"
            if not d["done"]:
                dtxt += "   " + (tr("overdue") if left < 0 else fmt_left(left))
            di = QTableWidgetItem(dtxt)
            if state == "overdue":
                di.setForeground(QColor("#e03131"))
            self.table.setItem(r, 2, di)
            pi = QTableWidgetItem("  " + tr("prio_" + d["priority"]))
            pi.setForeground(QColor(PRIO_COLORS[d["priority"]]))
            pf = pi.font()
            pf.setBold(True)
            pi.setFont(pf)
            self.table.setItem(r, 3, pi)
            self.table.setItem(r, 4, QTableWidgetItem(d.get("subject", "")))
        self.empty.setVisible(not rows)

    def _cell_clicked(self, r, col):
        if col == 0:
            self.toggle()

    def _cur(self):
        r = self.table.currentRow()
        if r < 0 or not self.table.item(r, 0):
            return None
        return self.win.store.get("deadlines", self.table.item(r, 0).data(Qt.UserRole))

    def quick_add(self):
        t = self.q_title.text().strip()
        if not t:
            self.q_title.setFocus()
            return
        self.win.store.upsert("deadlines", {"title": t, "due": self.q_due.dateTime().toString("yyyy-MM-ddTHH:mm"),
                                            "priority": self.q_prio.currentData(), "subject": "", "notes": "",
                                            "done": False})
        self.q_title.clear()
        self.win.refresh_all()
        self.win.status(tr("task_added"))

    def toggle(self):
        d = self._cur()
        if d:
            d["done"] = not d["done"]
            self.win.store.save()
            self.win.refresh_all()

    def edit(self):
        d = self._cur()
        if d:
            self.win.edit_deadline(d)

    def delete(self):
        d = self._cur()
        if d and ask(self, tr("confirm_delete_task", name=d["title"])):
            self.win.store.delete("deadlines", d["id"])
            self.win.refresh_all()


# =========================================================================== Sozlamalar
class SettingsPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        st = win.store
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        host = QWidget()
        scroll.setWidget(host)
        outer.addWidget(scroll)
        lay = QHBoxLayout(host)
        lay.setSpacing(16)
        lay.setContentsMargins(0, 0, 8, 0)
        # para vaqtlari
        pc = Card(tr("pairs_title"))
        h = QLabel(tr("pairs_hint"))
        h.setObjectName("Muted")
        h.setWordWrap(True)
        pc.add(h)
        self.pairs = QTableWidget(0, 2)
        self.pairs.setHorizontalHeaderLabels([tr("t_start"), tr("t_end")])
        self.pairs.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.pairs.verticalHeader().setDefaultSectionSize(38)
        self.pairs.setMinimumHeight(250)
        pc.add(self.pairs)
        pr = QHBoxLayout()
        ap = QPushButton(tr("add_pair"))
        rp = QPushButton(tr("remove_pair"))
        sp = primary_button(tr("save_pairs"))
        pr.addWidget(ap)
        pr.addWidget(rp)
        pr.addStretch(1)
        pr.addWidget(sp)
        pc.add(pr)
        ap.clicked.connect(self._add_pair)
        rp.clicked.connect(self._remove_pair)
        sp.clicked.connect(self._save_pairs)
        lay.addWidget(pc, 1)
        col = QVBoxLayout()
        col.setSpacing(14)
        sem = Card(tr("semester"))
        f = QFormLayout()
        self.sem = QDateEdit()
        self.sem.setCalendarPopup(True)
        self.sem.setDisplayFormat("dd.MM.yyyy")
        self.sem.dateChanged.connect(self._sem_changed)
        f.addRow(tr("semester_start"), self.sem)
        sem.add(f)
        self.sem_info = QLabel()
        self.sem_info.setObjectName("Muted")
        self.sem_info.setWordWrap(True)
        sem.add(self.sem_info)
        dl = QLabel(tr("work_days"))
        sem.add(dl)
        drow = QHBoxLayout()
        self.day_cbs = []
        for d in range(7):
            cb = QCheckBox(tr(DAY_KEYS[d]))
            cb.toggled.connect(self._days_changed)
            self.day_cbs.append(cb)
            drow.addWidget(cb)
        drow.addStretch(1)
        sem.add(drow)
        col.addWidget(sem)
        nt = Card(tr("notifications"))
        nf = QFormLayout()
        self.min_before = QSpinBox()
        self.min_before.setRange(0, 120)
        self.min_before.setSuffix(" " + tr("min_short"))
        self.min_before.setValue(win.settings.get("class_minutes", 10))
        self.min_before.valueChanged.connect(lambda v: self._set("class_minutes", v))
        nf.addRow(tr("before_class"), self.min_before)
        nt.add(nf)
        self.dl_cbs = {}
        drow2 = QHBoxLayout()
        drow2.addWidget(QLabel(tr("before_deadline")))
        cur = set(win.deadline_offsets())
        for m_, key in ((1440, "off_1d"), (180, "off_3h"), (60, "off_1h")):
            cb = QCheckBox(tr(key))
            cb.setChecked(m_ in cur)
            cb.toggled.connect(self._offs_changed)
            self.dl_cbs[m_] = cb
            drow2.addWidget(cb)
        drow2.addStretch(1)
        nt.add(drow2)
        self.tray_cb = QCheckBox(tr("minimize_to_tray"))
        self.tray_cb.setChecked(win.settings.get("minimize_to_tray", True))
        self.tray_cb.toggled.connect(lambda v: (self._set("minimize_to_tray", v), win.apply_tray_mode()))
        nt.add(self.tray_cb)
        self.auto_cb = QCheckBox(tr("autostart"))
        self.auto_cb.setChecked(is_autostart(AUTOSTART_NAME))
        self.auto_cb.toggled.connect(self._autostart)
        nt.add(self.auto_cb)
        tb = QPushButton(tr("test_notification"))
        tb.clicked.connect(lambda: win.tray.notify(tr("app_short"), tr("test_text")))
        r = QHBoxLayout()
        r.addWidget(tb)
        r.addStretch(1)
        nt.add(r)
        col.addWidget(nt)
        dc = Card(tr("data"))
        r2 = QHBoxLayout()
        ex = QPushButton(tr("export_json"))
        ex.setIcon(icon("export", pal()["text"]))
        im = QPushButton(tr("import_json"))
        im.setIcon(icon("import", pal()["text"]))
        r2.addWidget(ex)
        r2.addWidget(im)
        r2.addStretch(1)
        dc.add(r2)
        ex.clicked.connect(win.export_json)
        im.clicked.connect(win.import_json)
        col.addWidget(dc)
        col.addStretch(1)
        lay.addLayout(col, 1)
        self.load()

    def _set(self, k, v):
        if not is_demo():
            self.win.settings.set(k, v)

    def load(self):
        st = self.win.store
        self.pairs.setRowCount(0)
        for p in st.pairs:
            self._add_pair(p["start"], p["end"])
        d = st.semester_start
        self.sem.blockSignals(True)
        self.sem.setDate(QDate(d.year, d.month, d.day))
        self.sem.blockSignals(False)
        for i, cb in enumerate(self.day_cbs):
            cb.blockSignals(True)
            cb.setChecked(i in st.data["days"])
            cb.blockSignals(False)
        self._sem_info()

    def _sem_info(self):
        n = now().date()
        self.sem_info.setText(tr("sem_info", w=week_label(self.win.store, n)))

    def _add_pair(self, s=None, e=None):
        r = self.pairs.rowCount()
        self.pairs.insertRow(r)
        if not isinstance(s, str):
            prev = self.pairs.cellWidget(r - 1, 1).time() if r > 0 else QTime(8, 0)
            st_ = prev.addSecs(10 * 60)
            s, e = st_.toString("HH:mm"), st_.addSecs(80 * 60).toString("HH:mm")
        for c, v in ((0, s), (1, e)):
            te = QTimeEdit(QTime.fromString(v, "HH:mm"))
            te.setDisplayFormat("HH:mm")
            self.pairs.setCellWidget(r, c, te)

    def _remove_pair(self):
        if self.pairs.rowCount() > 1:
            self.pairs.removeRow(self.pairs.rowCount() - 1)

    def _save_pairs(self):
        pairs = []
        for r in range(self.pairs.rowCount()):
            s, e = self.pairs.cellWidget(r, 0).time(), self.pairs.cellWidget(r, 1).time()
            if e <= s:
                warn(self, tr("pair_invalid", n=r + 1))
                return
            if pairs and s < QTime.fromString(pairs[-1]["end"], "HH:mm"):
                warn(self, tr("pair_overlap", n=r + 1))
                return
            pairs.append({"start": s.toString("HH:mm"), "end": e.toString("HH:mm")})
        st = self.win.store
        lost = [l for l in st.lessons if int(l["pair"]) > len(pairs)]
        if lost and not ask(self, tr("pairs_lost", n=len(lost))):
            return
        st.data["pairs"] = pairs
        st.data["lessons"] = [l for l in st.lessons if int(l["pair"]) <= len(pairs)]
        st.save()
        self.win.refresh_all()
        self.win.status(tr("saved"))

    def _sem_changed(self, qd):
        self.win.store.data["semester_start"] = date(qd.year(), qd.month(), qd.day()).isoformat()
        self.win.store.save()
        self._sem_info()
        self.win.refresh_all(skip_settings=True)

    def _days_changed(self):
        days = [i for i, cb in enumerate(self.day_cbs) if cb.isChecked()]
        if not days:
            return
        self.win.store.data["days"] = days
        self.win.store.save()
        self.win.refresh_all(skip_settings=True)

    def _offs_changed(self):
        self._set("deadline_offsets", [m for m, cb in self.dl_cbs.items() if cb.isChecked()])

    def _autostart(self, v):
        if is_demo():
            return
        if not set_autostart(AUTOSTART_NAME, v, autostart_command("--tray")):
            error(self, tr("autostart_failed"))
            self.auto_cb.blockSignals(True)
            self.auto_cb.setChecked(not v)
            self.auto_cb.blockSignals(False)


# =========================================================================== demo
def demo_data() -> dict:
    d = sc.default_data()
    today = date.today()
    d["semester_start"] = sc.default_semester_start(today).isoformat()
    L = [
        ("Kompyuter grafikasi", "lecture", "KI-21", "A-305", 0, 1, "all"),
        ("Kompyuter grafikasi", "lab", "KI-21/1", "Lab-2", 0, 2, "odd"),
        ("Kompyuter grafikasi", "lab", "KI-21/2", "Lab-2", 0, 2, "even"),
        ("Dasturlash asoslari", "lecture", "DI-22", "B-112", 1, 2, "all"),
        ("Dasturlash asoslari", "practice", "DI-22", "B-207", 1, 3, "all"),
        ("Ma'lumotlar bazasi", "lecture", "KI-21, KI-22", "A-401", 2, 1, "all"),
        ("Ma'lumotlar bazasi", "lab", "KI-22", "Lab-4", 2, 3, "odd"),
        ("Kompyuter grafikasi", "practice", "KI-22", "A-305", 3, 1, "all"),
        ("Dasturlash asoslari", "lab", "DI-22", "Lab-1", 3, 2, "all"),
        ("Ma'lumotlar bazasi", "practice", "KI-21", "B-207", 3, 3, "even"),
        ("Ilmiy seminar", "seminar", "Magistrlar", "Kafedra", 3, 4, "all"),
        ("Web dasturlash", "lecture", "DI-23", "A-210", 4, 2, "all"),
        ("Web dasturlash", "lab", "DI-23", "Lab-3", 4, 3, "all"),
        ("Dasturlash asoslari", "practice", "DI-22", "B-207", 5, 1, "odd"),
    ]
    for i, (s, t, g, r, day, pair, w) in enumerate(L, 1):
        d["lessons"].append({"id": i, "subject": s, "type": t, "group": g, "room": r, "notes": "", "day": day,
                             "pair": pair, "week": w, "color": ""})
    base = now()
    T = [
        ("Laboratoriya ishlarini tekshirish (KI-21)", 0.2, "high", "Kompyuter grafikasi"),
        ("Maqola qo'lyozmasini jurnalga yuborish", 1.3, "high", ""),
        ("Oraliq nazorat savollarini tayyorlash", 3, "medium", "Ma'lumotlar bazasi"),
        ("Kafedra yig'ilishi uchun hisobot", 5, "medium", ""),
        ("Ma'ruza slaydlarini yangilash", 8, "low", "Web dasturlash"),
        ("Magistrant dissertatsiya bobini o'qish", -0.5, "medium", "Ilmiy seminar"),
    ]
    nid = len(L) + 1
    for title, days, pr, subj in T:
        due = (base + timedelta(days=days)).replace(second=0, microsecond=0)
        d["deadlines"].append({"id": nid, "title": title, "due": due.isoformat(timespec="minutes"), "priority": pr,
                               "subject": subj, "notes": "", "done": False})
        nid += 1
    d["deadlines"].append({"id": nid, "title": "Fan dasturini tasdiqlatish", "due":
                           (base - timedelta(days=2)).isoformat(timespec="minutes"), "priority": "medium",
                           "subject": "", "notes": "", "done": True})
    d["next_id"] = nid + 1
    return d


# =========================================================================== asosiy oyna
class NavButton(QPushButton):
    def __init__(self, text, icon_name):
        super().__init__(text)
        self.icon_name = icon_name
        self.setCheckable(True)
        self.setObjectName("TopNav")
        self.setIconSize(QSize(18, 18))
        self.setCursor(Qt.PointingHandCursor)
        self.recolor()

    def recolor(self):
        self.setIcon(icon(self.icon_name, accent() if self.isChecked() else pal()["muted"]))


class PageCount:
    """BaseMainWindow._nav o'rnida: tekshiruv vositalari sahifalar sonini bilishi uchun."""

    def __init__(self, stack):
        self.stack = stack

    def count(self):
        return self.stack.count()


class MainWindow(BaseMainWindow):
    def __init__(self):
        super().__init__()
        data = app_data_dir(SLUG)
        self.store = sc.Store(data / "jadval.json")
        if is_demo():
            self.store.data = demo_data()
        root = QWidget()
        rl = QVBoxLayout(root)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        top = QFrame()
        top.setObjectName("TopBar")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(18, 8, 18, 8)
        tl.setSpacing(4)
        logo = QLabel()
        logo.setPixmap(QIcon(str(resource("assets", "icon.png"))).pixmap(26, 26))
        tl.addWidget(logo)
        name = QLabel(tr("app_short"))
        name.setObjectName("AppName")
        tl.addWidget(name)
        tl.addSpacing(18)
        self.nav = QButtonGroup(self)
        self.nav_btns = []
        for i, (key, ic) in enumerate((("page_today", "clock"), ("page_week", "calendar"), ("page_tasks", "tasks"),
                                       ("page_settings", "gear"))):
            b = NavButton(tr(key), ic)
            self.nav.addButton(b, i)
            self.nav_btns.append(b)
            tl.addWidget(b)
        tl.addStretch(1)
        self.clock = QLabel()
        self.clock.setObjectName("Clock")
        tl.addWidget(self.clock)
        rl.addWidget(top)
        self.stack = QStackedWidget()
        self.today = TodayPage(self)
        self.week = WeekPage(self)
        self.tasks = TasksPage(self)
        self.settings_page = None
        self.tray = Tray(self, QIcon(str(resource("assets", "icon.ico"))))
        self.settings_page = SettingsPage(self)
        for w in (self.today, self.week, self.tasks, self.settings_page):
            holder = QWidget()
            hl = QVBoxLayout(holder)
            hl.setContentsMargins(20, 16, 20, 14)
            hl.addWidget(w)
            self.stack.addWidget(holder)
        rl.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self.nav.idClicked.connect(self.set_page)
        self._nav = PageCount(self.stack)   # uzkit/verify: sahifalar soni

        start_page = 0 if is_demo() else int(self.settings.get("last_page", 0) or 0)
        self.set_page(start_page)

        act = QAction(tr("add_task"), self)
        act.setShortcut("Ctrl+N")
        act.triggered.connect(lambda: self.add_deadline())
        act2 = QAction(tr("add_lesson"), self)
        act2.setShortcut("Ctrl+L")
        act2.triggered.connect(lambda: self.add_lesson())
        first = self.menu_file.actions()[0]
        for a in (act, act2):
            self.menu_file.insertAction(first, a)
        self.menu_file.insertSeparator(first)
        ex = QAction(tr("export_json"), self)
        ex.triggered.connect(self.export_json)
        im = QAction(tr("import_json"), self)
        im.triggered.connect(self.import_json)
        self.menu_file.insertAction(first, ex)
        self.menu_file.insertAction(first, im)
        self.menu_file.insertSeparator(first)

        self.refresh_all()
        self._tick()
        self.ticker = QTimer(self)
        self.ticker.timeout.connect(self._tick)
        self.ticker.start(30_000)
        if not is_demo() and "--selftest" not in sys.argv and "pytest" not in sys.modules:
            self.tray.show()
            self.apply_tray_mode()
            QTimer.singleShot(3000, self.check_notifications)
            if "--tray" in sys.argv and self.settings.get("minimize_to_tray", True) and self.tray.available():
                QTimer.singleShot(0, self.hide)

    # ------------------------------------------------------------------ navigatsiya
    def set_page(self, i: int):
        if not 0 <= i < self.stack.count():
            return
        self.stack.setCurrentIndex(i)
        self.nav.button(i).setChecked(True)
        for b in self.nav_btns:
            b.recolor()
        if not is_demo():
            self.settings.set("last_page", i, save=False)

    def refresh_all(self, skip_settings=False):
        self.today.refresh()
        self.week.refresh()
        self.tasks.refresh()
        if self.settings_page and not skip_settings:
            self.settings_page.load()

    def _tick(self):
        n = now()
        self.clock.setText(f"{n:%H:%M}   {week_label(self.store, n.date())}")
        if self.isVisible():
            self.today.refresh()
            if self.week.grid.model:
                self.week.grid.model.now = n
                self.week.grid.update()
        if not is_demo():
            self.check_notifications()

    def on_theme_changed(self):
        from .ui_extra import _ICON_CACHE
        _ICON_CACHE.clear()
        for b in self.nav_btns:
            b.recolor()
        self.refresh_all()

    def deadline_offsets(self):
        return self.settings.get("deadline_offsets", [1440, 60])

    def apply_tray_mode(self):
        on = self.settings.get("minimize_to_tray", True) and self.tray.available()
        QApplication.instance().setQuitOnLastWindowClosed(not on)

    # ------------------------------------------------------------------ darslar
    def add_lesson(self, day=None, pair=None):
        n = now()
        dlg = LessonDialog(self, self.store, None, n.weekday() if day is None else day, pair or 1)
        if dlg.exec():
            self.store.upsert("lessons", dlg.values())
            self.refresh_all()

    def edit_lesson(self, l):
        dlg = LessonDialog(self, self.store, l)
        if dlg.exec():
            self.store.upsert("lessons", dlg.values())
            self.refresh_all()

    def duplicate_lesson(self, l):
        c = dict(l)
        c.pop("id", None)
        dlg = LessonDialog(self, self.store, c)
        dlg.setWindowTitle(tr("duplicate"))
        if dlg.exec():
            v = dlg.values()
            v.pop("id", None)
            self.store.upsert("lessons", v)
            self.refresh_all()

    def delete_lesson(self, l):
        if ask(self, tr("confirm_delete_lesson", name=l["subject"])):
            self.store.delete("lessons", l["id"])
            self.refresh_all()

    # ------------------------------------------------------------------ vazifalar
    def add_deadline(self):
        dlg = DeadlineDialog(self, self.store)
        if dlg.exec():
            self.store.upsert("deadlines", dlg.values())
            self.refresh_all()

    def edit_deadline(self, d):
        dlg = DeadlineDialog(self, self.store, d)
        if dlg.exec():
            self.store.upsert("deadlines", dlg.values())
            self.refresh_all()

    # ------------------------------------------------------------------ JSON
    def export_json(self):
        path, _ = QFileDialog.getSaveFileName(self, tr("export_json"),
                                              str(Path.home() / f"dars_jadvali_{date.today():%Y%m%d}.json"),
                                              "JSON (*.json)")
        if not path:
            return
        try:
            Path(path).write_text(json.dumps(self.store.data, ensure_ascii=False, indent=1), encoding="utf-8")
            self.status(tr("saved_to", path=path))
        except Exception as ex:
            appmod.log_exception(ex)
            error(self, tr("export_error"))

    def import_json(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("import_json"), str(Path.home()), "JSON (*.json)")
        if not path:
            return
        try:
            new = sc.validate(json.loads(Path(path).read_text(encoding="utf-8")))
        except Exception as ex:
            appmod.log_exception(ex)
            error(self, tr("import_invalid"))
            return
        box = QMessageBox(QMessageBox.Question, tr("import_json"),
                          tr("import_how", l=len(new["lessons"]), d=len(new["deadlines"])), parent=self)
        b_merge = box.addButton(tr("merge"), QMessageBox.AcceptRole)
        b_repl = box.addButton(tr("replace"), QMessageBox.DestructiveRole)
        box.addButton(tr("cancel"), QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is b_merge:
            self.store.data = sc.merge(self.store.data, new)
        elif box.clickedButton() is b_repl:
            self.store.data = new
        else:
            return
        self.store.save()
        self.refresh_all()
        self.status(tr("imported"))

    # ------------------------------------------------------------------ eslatmalar
    def check_notifications(self):
        try:
            st = self.store
            n = datetime.now()
            for key, l, s in sc.class_notifications(st.lessons, st.pairs, n, st.semester_start,
                                                   int(self.settings.get("class_minutes", 10)), st.notified):
                st.mark_notified(key)
                mins = max(0, round((s - n).total_seconds() / 60))
                self.tray.notify(tr("class_soon", m=mins),
                                 f"{l['subject']} ({tr('type_' + l['type'])})\n{s:%H:%M}  "
                                 + "  ".join(x for x in (l.get("room", ""), l.get("group", "")) if x))
            due = sc.deadline_notifications(st.deadlines, n, self.deadline_offsets(), st.notified)
            for key, d, left in due:
                st.mark_notified(key)
            if due:
                lines = [f"{d['title']}: {tr('overdue') if left < 0 else fmt_left(left)}" for _, d, left in due]
                self.tray.notify(tr("deadline_soon"), "\n".join(lines[:4]))
        except Exception as ex:
            appmod.log_exception(ex)

    def closeEvent(self, e):
        if (not self.tray.quitting and self.settings.get("minimize_to_tray", True) and self.tray.available()
                and self.tray.icon.isVisible()):
            e.ignore()
            self.hide()
            if not self.settings.get("tray_hint_shown"):
                self.tray.notify(tr("app_short"), tr("tray_hint"))
                self.settings.set("tray_hint_shown", True)
            return
        if not is_demo():
            self.settings.save()
        super().closeEvent(e)
