"""Haftalik jadval to'ri: ekranda, PNG va PDF uchun bir xil QPainter chizish."""
from datetime import date, datetime, timedelta

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from uzkit.i18n import tr

from . import schedule as sc
from .ui_extra import mix, pal

DAY_KEYS = ["d_mon", "d_tue", "d_wed", "d_thu", "d_fri", "d_sat", "d_sun"]


class GridModel:
    """Chizish uchun tayyorlangan ma'lumot."""

    def __init__(self, store, week_monday: date, show_all: bool, now: datetime = None):
        self.pairs = store.pairs
        self.days = list(store.data["days"]) or [0, 1, 2, 3, 4]
        self.week_monday = week_monday
        self.show_all = show_all
        self.now = now or datetime.now()
        self.semester_start = store.semester_start
        self.week_no = sc.week_number(self.semester_start, week_monday)
        self.parity = sc.parity(self.week_no)
        self.color_of = store.color_of
        self.cells = {}
        for l in store.lessons:
            if l["day"] not in self.days:
                continue
            if not show_all and l.get("week", "all") not in ("all", self.parity):
                continue
            self.cells.setdefault((l["day"], int(l["pair"])), []).append(l)
        for v in self.cells.values():
            v.sort(key=lambda l: sc.WEEK_MODES.index(l.get("week", "all")))


def paint_week(p: QPainter, rect: QRectF, m: GridModel, colors: dict, hits: list = None, print_mode=False,
               hover=None):
    """Jadvalni rect ichiga chizadi. hits ro'yxatiga (QRectF, kun, para, dars|None) yoziladi."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    c = colors
    base = QFont(p.font())
    time_w = 74.0
    head_h = 46.0
    ncol = len(m.days)
    nrow = len(m.pairs)
    col_w = (rect.width() - time_w) / max(ncol, 1)
    row_h = (rect.height() - head_h) / max(nrow, 1)
    today = m.now.date()
    # ustun sarlavhalari
    for j, d in enumerate(m.days):
        x = rect.left() + time_w + j * col_w
        day_date = m.week_monday + timedelta(days=d)
        is_today = day_date == today and not print_mode
        hr = QRectF(x + 3, rect.top(), col_w - 6, head_h - 6)
        if is_today:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(c["accent"]))
            p.drawRoundedRect(hr, 8, 8)
        f = QFont(base)
        f.setBold(True)
        f.setPointSizeF(10)
        p.setFont(f)
        p.setPen(QColor("#ffffff") if is_today else QColor(c["text"]))
        p.drawText(QRectF(hr.left(), hr.top() + 3, hr.width(), hr.height() / 2), Qt.AlignCenter,
                   tr(DAY_KEYS[d]))
        f.setBold(False)
        f.setPointSizeF(8.5)
        p.setFont(f)
        p.setPen(QColor("#ffffff") if is_today else QColor(c["muted"]))
        p.drawText(QRectF(hr.left(), hr.center().y(), hr.width(), hr.height() / 2 - 2), Qt.AlignCenter,
                   day_date.strftime("%d.%m"))
    # qatorlar
    for i, pr in enumerate(m.pairs):
        y = rect.top() + head_h + i * row_h
        f = QFont(base)
        f.setBold(True)
        f.setPointSizeF(11)
        p.setFont(f)
        p.setPen(QColor(c["text"]))
        p.drawText(QRectF(rect.left(), y + 4, time_w - 10, row_h / 2 - 2), Qt.AlignRight | Qt.AlignBottom,
                   f"{i + 1}")
        f.setBold(False)
        f.setPointSizeF(8.3)
        p.setFont(f)
        p.setPen(QColor(c["muted"]))
        p.drawText(QRectF(rect.left(), y + row_h / 2 + 1, time_w - 10, row_h / 2 - 4), Qt.AlignRight | Qt.AlignTop,
                   f"{pr['start']}\n{pr['end']}")
        p.setPen(QPen(QColor(c["border"]), 1))
        p.drawLine(QPointF(rect.left() + time_w, y), QPointF(rect.right(), y))
    p.setPen(QPen(QColor(c["border"]), 1))
    p.drawLine(QPointF(rect.left() + time_w, rect.bottom()), QPointF(rect.right(), rect.bottom()))
    # bugungi ustun foni
    for j, d in enumerate(m.days):
        x = rect.left() + time_w + j * col_w
        if m.week_monday + timedelta(days=d) == today and not print_mode:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(mix(c["accent"], c["surface"], 0.94)))
            p.drawRect(QRectF(x, rect.top() + head_h, col_w, rect.height() - head_h))
    # kataklar
    type_names = {t: tr(f"type_{t}") for t in sc.LESSON_TYPES}
    for j, d in enumerate(m.days):
        x = rect.left() + time_w + j * col_w
        for i in range(nrow):
            y = rect.top() + head_h + i * row_h
            cell = QRectF(x + 3, y + 3, col_w - 6, row_h - 6)
            items = m.cells.get((d, i + 1), [])
            if not items:
                if hits is not None:
                    hits.append((cell, d, i + 1, None))
                if hover == (d, i + 1) and not print_mode:
                    p.setPen(QPen(QColor(c["accent"]), 1.2, Qt.DashLine))
                    p.setBrush(Qt.NoBrush)
                    p.drawRoundedRect(cell, 8, 8)
                    p.setPen(QColor(c["accent"]))
                    f = QFont(base)
                    f.setPointSizeF(15)
                    p.setFont(f)
                    p.drawText(cell, Qt.AlignCenter, "+")
                continue
            n = len(items)
            sub_w = (cell.width() - 4 * (n - 1)) / n
            for k, l in enumerate(items):
                r = QRectF(cell.left() + k * (sub_w + 4), cell.top(), sub_w, cell.height())
                if hits is not None:
                    hits.append((r, d, i + 1, l))
                _paint_card(p, r, l, c, type_names, base, compact=n > 1, color=m.color_of(l))
    # "hozir" chizig'i
    if not print_mode and m.week_monday <= today < m.week_monday + timedelta(days=7) and today.weekday() in m.days:
        j = m.days.index(today.weekday())
        x = rect.left() + time_w + j * col_w
        yy = _now_y(m, rect.top() + head_h, row_h)
        if yy is not None:
            p.setPen(QPen(QColor("#e03131"), 2))
            p.drawLine(QPointF(x + 2, yy), QPointF(x + col_w - 2, yy))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#e03131"))
            p.drawEllipse(QPointF(x + 4, yy), 4, 4)
    p.restore()


def _now_y(m: GridModel, top, row_h):
    t = m.now
    for i, pr in enumerate(m.pairs):
        st = datetime.combine(t.date(), sc.parse_hm(pr["start"]))
        en = datetime.combine(t.date(), sc.parse_hm(pr["end"]))
        if st <= t <= en:
            frac = (t - st).total_seconds() / max((en - st).total_seconds(), 1)
            return top + i * row_h + 3 + frac * (row_h - 6)
        if i + 1 < len(m.pairs):
            nst = datetime.combine(t.date(), sc.parse_hm(m.pairs[i + 1]["start"]))
            if en < t < nst:
                return top + (i + 1) * row_h
    return None


def _paint_card(p, r: QRectF, l: dict, c: dict, type_names: dict, base: QFont, compact=False, color=None):
    col = color or l.get("color") or sc.subject_color(l["subject"])
    bg = mix(col, c["surface"], 0.84)
    path = QPainterPath()
    path.addRoundedRect(r, 8, 8)
    p.fillPath(path, bg)
    p.save()
    p.setClipPath(path)
    p.fillRect(QRectF(r.left(), r.top(), 4, r.height()), QColor(col))
    p.restore()
    pad = 9
    inner = r.adjusted(pad + 2, 6, -6, -5)
    f = QFont(base)
    f.setBold(True)
    f.setPointSizeF(9.6 if not compact else 8.8)
    p.setFont(f)
    fm = p.fontMetrics()
    text_col = QColor(mix(col, c["text"], 0.55))
    p.setPen(text_col)
    lines = _wrap(fm, l["subject"], inner.width(), 2)
    y = inner.top()
    for ln in lines:
        p.drawText(QRectF(inner.left(), y, inner.width(), fm.height()), Qt.AlignLeft | Qt.AlignVCenter, ln)
        y += fm.height()
    f.setBold(False)
    f.setPointSizeF(8.2)
    p.setFont(f)
    fm2 = p.fontMetrics()
    # turi va hafta belgisi
    tag = type_names.get(l.get("type"), "")
    if l.get("week", "all") != "all":
        tag += " · " + tr("wk_" + l["week"])
    p.setPen(QColor(col))
    if y + fm2.height() <= inner.bottom() + 2:
        p.drawText(QRectF(inner.left(), y + 1, inner.width(), fm2.height()), Qt.AlignLeft | Qt.AlignVCenter,
                   fm2.elidedText(tag, Qt.ElideRight, int(inner.width())))
        y += fm2.height() + 1
    p.setPen(QColor(c["muted"]))
    info = "  ".join(x for x in (l.get("room", ""), l.get("group", "")) if x)
    if info and y + fm2.height() <= inner.bottom() + 3:
        p.drawText(QRectF(inner.left(), y, inner.width(), fm2.height()), Qt.AlignLeft | Qt.AlignVCenter,
                   fm2.elidedText(info, Qt.ElideRight, int(inner.width())))


def _wrap(fm, text, width, max_lines):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        cand = (cur + " " + w).strip()
        if fm.horizontalAdvance(cand) <= width or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = fm.elidedText(lines[-1] + " …", Qt.ElideRight, int(width))
    return [fm.elidedText(x, Qt.ElideRight, int(width)) for x in lines]


class WeekGrid(QWidget):
    empty_clicked = Signal(int, int)        # kun, para
    lesson_activated = Signal(dict)          # ikki marta bosish
    lesson_menu = Signal(dict, object)       # o'ng tugma: dars, global nuqta

    def __init__(self):
        super().__init__()
        self.model = None
        self.hits = []
        self.hover = None
        self.setMouseTracking(True)
        self.setMinimumHeight(380)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_model(self, m: GridModel):
        self.model = m
        self.update()

    def colors(self):
        c = pal()
        from .ui_extra import accent
        c["accent"] = accent()
        return c

    def paintEvent(self, e):
        if not self.model:
            return
        p = QPainter(self)
        self.hits = []
        paint_week(p, QRectF(self.rect()).adjusted(2, 2, -4, -4), self.model, self.colors(), self.hits,
                   hover=self.hover)

    def _hit(self, pos):
        for r, d, pr, l in self.hits:
            if r.contains(QPointF(pos)):
                return d, pr, l
        return None

    def mouseMoveEvent(self, e):
        h = self._hit(e.position())
        hv = (h[0], h[1]) if h and h[2] is None else None
        self.setCursor(Qt.PointingHandCursor if h else Qt.ArrowCursor)
        if h and h[2] is not None:
            l = h[2]
            self.setToolTip(f"{l['subject']}\n{tr('type_' + l['type'])}  {l.get('room', '')}  {l.get('group', '')}"
                            + (f"\n{l['notes']}" if l.get("notes") else ""))
        else:
            self.setToolTip("")
        if hv != self.hover:
            self.hover = hv
            self.update()

    def leaveEvent(self, e):
        self.hover = None
        self.update()

    def mouseReleaseEvent(self, e):
        h = self._hit(e.position())
        if not h:
            return
        if e.button() == Qt.LeftButton and h[2] is None:
            self.empty_clicked.emit(h[0], h[1])
        elif e.button() == Qt.RightButton and h[2] is not None:
            self.lesson_menu.emit(h[2], e.globalPosition().toPoint())

    def mouseDoubleClickEvent(self, e):
        h = self._hit(e.position())
        if h and h[2] is not None:
            self.lesson_activated.emit(h[2])
