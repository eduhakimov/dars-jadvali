"""Chuqur ssenariylar: soxta soat bilan butun kun/hafta eslatmalari, buzilgan fayl, interfeys oqimi.

Hech qanday haqiqiy rejalashtirilgan vazifa yoki avtoyuklash yaratilmaydi (set_autostart sinovda taqiqlangan).
"""
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dars_jadvali import schedule as sc  # noqa: E402

PAIRS = [{"start": s, "end": e} for s, e in sc.DEFAULT_PAIRS]
SEM = date(2026, 9, 1)                    # seshanba; 1-hafta 31-avgust dushanbadan


def _lesson(i, day, pair, week="all", subject="Fan"):
    return {"id": i, "subject": subject, "type": "lecture", "group": "", "room": "", "notes": "", "day": day,
            "pair": pair, "week": week, "color": ""}


def _minutes(start: datetime, end: datetime, step=1):
    t = start
    while t <= end:
        yield t
        t += timedelta(minutes=step)


def test_class_reminders_over_two_weeks_minute_by_minute():
    lessons = [_lesson(1, 0, 1, "odd", "Matematika"), _lesson(2, 0, 2, "even", "Fizika"),
               _lesson(3, 0, 3, "all", "Tarix")]
    notified, got = set(), []
    for monday in (date(2026, 9, 7), date(2026, 9, 14)):        # 2-hafta (juft), 3-hafta (toq)
        for now in _minutes(datetime.combine(monday, datetime.min.time()).replace(hour=7),
                            datetime.combine(monday, datetime.min.time()).replace(hour=13)):
            for key, l, st in sc.class_notifications(lessons, PAIRS, now, SEM, 10, notified):
                notified.add(key)
                got.append((now.strftime("%d %H:%M"), l["subject"]))
    assert got == [("07 09:50", "Fizika"), ("07 11:20", "Tarix"),
                   ("14 08:20", "Matematika"), ("14 11:20", "Tarix")]


def test_deadline_reminders_minute_by_minute():
    due = datetime(2026, 10, 5, 9, 0)
    dls = [{"id": 1, "title": "Kurs ishi", "due": due.isoformat(timespec="minutes"), "done": False},
           {"id": 2, "title": "Bajarilgan", "due": due.isoformat(timespec="minutes"), "done": True}]
    notified, got = set(), []
    for now in _minutes(due - timedelta(days=2), due + timedelta(days=2), 5):
        for key, d, left in sc.deadline_notifications(dls, now, [1440, 60], notified):
            notified.add(key)
            got.append((now, key.rsplit(":", 1)[1]))
    assert got == [(due - timedelta(days=1), "m1440"), (due - timedelta(minutes=60), "m60"), (due + timedelta(minutes=5), "over")]


def test_week_parity_across_new_year_and_semester_edges():
    assert sc.week_number(SEM, date(2026, 8, 31)) == 1
    assert sc.week_number(SEM, date(2026, 8, 30)) == 0 and sc.parity(0) == "even"
    assert sc.parity(sc.week_number(SEM, date(2027, 1, 4))) == sc.parity(19)
    assert sc.next_class([_lesson(1, 0, 1, "odd")], PAIRS, datetime(2026, 9, 7, 8, 0), SEM)[1] == \
        datetime(2026, 9, 14, 8, 30)                             # 7-sentabr juft hafta, keyingisi 14-da


def test_corrupt_store_is_backed_up(tmp_path):
    f = tmp_path / "jadval.json"
    f.write_text("{bad json", encoding="utf-8")
    (tmp_path / "notified.json").write_text("not a list", encoding="utf-8")
    st = sc.Store(f)
    assert st.lessons == [] and (tmp_path / "jadval.broken.json").exists()
    st.upsert("lessons", _lesson(None, 1, 1))
    assert json.loads(f.read_text(encoding="utf-8"))["lessons"][0]["subject"] == "Fan"


def test_import_rejects_bad_files():
    for bad in ([], {"pairs": []}, {"pairs": [{"start": "10:00", "end": "09:00"}]},
                {"lessons": [{"subject": "A", "day": 9, "pair": 1}]},
                {"deadlines": [{"title": "X", "due": "ertaga"}]}):
        with pytest.raises(Exception):
            sc.validate(bad)


# ----------------------------------------------------------------------------- interfeys + soxta soat
class _FakeDT(datetime):
    current = datetime(2026, 9, 7, 8, 0)

    @classmethod
    def now(cls, tz=None):
        return cls.current


@pytest.fixture
def win(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    from PySide6.QtWidgets import QApplication
    from uzkit import app as appmod
    from uzkit.settings import Settings
    appmod.META = appmod.load_meta()
    appmod.SETTINGS = Settings(appmod.META["slug"] + "_scn")
    QApplication.instance() or QApplication([])
    from dars_jadvali import ui_extra, window as wmod
    monkeypatch.setattr(ui_extra, "_DEMO_DIRS", {})
    monkeypatch.setattr(wmod, "set_autostart", lambda *a, **k: pytest.fail("autostart must not be touched"))
    monkeypatch.setattr(wmod, "datetime", _FakeDT)
    w = wmod.MainWindow()
    sent = []
    monkeypatch.setattr(w.tray, "notify", lambda title, text, ms=0: sent.append((title, text)))
    w.sent = sent
    yield w
    w.tray.quitting = True
    w.close()


def test_ui_notifications_with_mocked_clock(win):
    st = win.store
    st.data["semester_start"] = SEM.isoformat()
    st.upsert("lessons", {**_lesson(None, 0, 2, "even", "Fizika"), "room": "204", "group": "AT-21"})
    st.upsert("deadlines", {"title": "Laboratoriya hisoboti", "due": "2026-09-08T12:00", "priority": "high",
                            "subject": "Fizika", "notes": "", "done": False})
    _FakeDT.current = datetime(2026, 9, 7, 9, 40)              # darsga 20 daqiqa: hali erta
    win.check_notifications()
    assert win.sent == []
    _FakeDT.current = datetime(2026, 9, 7, 9, 52)
    win.check_notifications()
    titles = [t for t, _ in win.sent]
    texts = "\n".join(x for _, x in win.sent)
    assert len(win.sent) == 1 and "Fizika" in texts and "10:00" in texts and "204" in texts
    win.check_notifications()                               # bir daqiqadan keyin takrorlanmaydi
    assert len(win.sent) == 1
    _FakeDT.current = datetime(2026, 9, 7, 12, 5)             # muddatga 24 soatdan kam
    win.check_notifications()
    assert len(win.sent) == 2 and "Laboratoriya hisoboti" in win.sent[1][1]
    assert titles
    # eslatma kalitlari faylga yozilgan: dastur qayta ochilsa ham takrorlanmaydi
    saved = json.loads(st.notified_path.read_text(encoding="utf-8"))
    assert len(saved) == 2


def test_ui_bad_offset_settings_do_not_break_reminders(win):
    win.settings.set("deadline_offsets", ["x", 60, -5])
    win.settings.set("class_minutes", "abc")
    win.store.upsert("deadlines", {"title": "T", "due": "2026-09-07T12:00", "priority": "low",
                                   "subject": "", "notes": "", "done": False})
    _FakeDT.current = datetime(2026, 9, 7, 11, 30)
    win.check_notifications()
    assert any("T" in x for _, x in win.sent)


def test_ui_starts_with_wrong_typed_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    from PySide6.QtWidgets import QApplication
    from uzkit import app as appmod
    from uzkit.settings import Settings
    appmod.META = appmod.load_meta()
    s = Settings(appmod.META["slug"] + "_bad")
    s.set("class_minutes", "abc")
    s.set("deadline_offsets", "60")
    appmod.SETTINGS = Settings(appmod.META["slug"] + "_bad")
    QApplication.instance() or QApplication([])
    from dars_jadvali import ui_extra, window as wmod
    monkeypatch.setattr(ui_extra, "_DEMO_DIRS", {})
    w = wmod.MainWindow()
    assert w.class_minutes() == 10 and w.deadline_offsets() == [1440, 60]
    w.tray.quitting = True
    w.close()
