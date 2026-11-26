import json
import os
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dars_jadvali import schedule as sc

START = date(2026, 9, 1)   # seshanba


def L(i, day, pair, week="all", subject="Fan"):
    return {"id": i, "subject": subject, "type": "lecture", "group": "G", "room": "R", "notes": "", "day": day,
            "pair": pair, "week": week, "color": ""}


def test_week_number_and_parity():
    assert sc.week_number(START, date(2026, 9, 1)) == 1
    assert sc.week_number(START, date(2026, 8, 31)) == 1      # o'sha haftaning dushanbasi
    assert sc.week_number(START, date(2026, 9, 6)) == 1       # yakshanba
    assert sc.week_number(START, date(2026, 9, 7)) == 2
    assert sc.week_number(START, date(2026, 12, 28)) == 18
    assert sc.parity(1) == "odd" and sc.parity(2) == "even" and sc.parity(0) == "even" and sc.parity(-1) == "odd"


def test_occurs_odd_even():
    odd = L(1, 0, 1, "odd")
    even = L(2, 0, 1, "even")
    allw = L(3, 0, 2)
    mon_w1, mon_w2 = date(2026, 8, 31), date(2026, 9, 7)
    assert sc.occurs(odd, mon_w1, START) and not sc.occurs(even, mon_w1, START)
    assert sc.occurs(even, mon_w2, START) and not sc.occurs(odd, mon_w2, START)
    assert sc.occurs(allw, mon_w2, START)
    assert not sc.occurs(allw, date(2026, 9, 8), START)
    assert [l["id"] for l in sc.lessons_on([allw, odd, even], mon_w1, START)] == [1, 3]


def test_next_class_and_running():
    pairs = [{"start": s, "end": e} for s, e in sc.DEFAULT_PAIRS]
    lessons = [L(1, 0, 1), L(2, 0, 3), L(3, 2, 2)]
    mon = date(2026, 9, 7)
    r = sc.next_class(lessons, pairs, datetime(2026, 9, 7, 8, 0), START)
    assert r[0]["id"] == 1 and r[1] == datetime(2026, 9, 7, 8, 30) and not r[3]
    r = sc.next_class(lessons, pairs, datetime(2026, 9, 7, 9, 0), START)
    assert r[0]["id"] == 1 and r[3]
    r = sc.next_class(lessons, pairs, datetime(2026, 9, 7, 13, 0), START)
    assert r[0]["id"] == 3 and r[1].date() == mon + timedelta(days=2)
    assert sc.next_class([], pairs, datetime(2026, 9, 7, 13, 0), START) is None


def test_class_notifications():
    pairs = [{"start": s, "end": e} for s, e in sc.DEFAULT_PAIRS]
    lessons = [L(1, 0, 1), L(2, 0, 2)]
    n = datetime(2026, 9, 7, 8, 22)
    out = sc.class_notifications(lessons, pairs, n, START, 10, set())
    assert [x[1]["id"] for x in out] == [1]
    keys = {x[0] for x in out}
    assert sc.class_notifications(lessons, pairs, n, START, 10, keys) == []
    assert sc.class_notifications(lessons, pairs, datetime(2026, 9, 7, 8, 31), START, 10, set()) == []


def test_deadline_notifications():
    n = datetime(2026, 3, 1, 12, 0)
    dls = [{"id": 1, "title": "a", "due": "2026-03-02T10:00", "done": False},
           {"id": 2, "title": "b", "due": "2026-03-01T12:30", "done": False},
           {"id": 3, "title": "c", "due": "2026-03-05T10:00", "done": False},
           {"id": 4, "title": "d", "due": "2026-03-01T11:00", "done": False},
           {"id": 5, "title": "e", "due": "2026-03-01T12:30", "done": True}]
    out = sc.deadline_notifications(dls, n, [1440, 60], set())
    keys = {k for k, _, _ in out}
    assert keys == {"D1:2026-03-02T10:00:m1440", "D2:2026-03-01T12:30:m60", "D4:2026-03-01T11:00:over"}
    assert sc.deadline_notifications(dls, n, [1440, 60], keys) == []


def test_filter_deadlines():
    n = datetime(2026, 3, 1, 12, 0)
    dls = [{"id": 1, "title": "a", "due": "2026-03-03T10:00", "priority": "low", "done": False},
           {"id": 2, "title": "b", "due": "2026-02-28T10:00", "priority": "high", "done": False},
           {"id": 3, "title": "c", "due": "2026-03-02T10:00", "priority": "high", "done": True}]
    assert [d["id"] for d in sc.filter_deadlines(dls, "active", n)] == [2, 1]
    assert [d["id"] for d in sc.filter_deadlines(dls, "overdue", n)] == [2]
    assert [d["id"] for d in sc.filter_deadlines(dls, "done", n)] == [3]
    assert len(sc.filter_deadlines(dls, "all", n)) == 3


def test_validate_and_merge_roundtrip():
    d = sc.default_data()
    d["lessons"] = [L(1, 0, 1, "odd", "A"), L(2, 1, 2, "all", "B")]
    d["deadlines"] = [{"id": 3, "title": "t", "due": "2026-03-01T10:00", "priority": "high"}]
    v = sc.validate(json.loads(json.dumps(d)))
    assert len(v["lessons"]) == 2 and v["lessons"][0]["week"] == "odd"
    assert v["deadlines"][0]["done"] is False
    m = sc.merge(v, v)
    assert len(m["lessons"]) == 2 and len(m["deadlines"]) == 1
    other = sc.validate({"lessons": [L(9, 3, 3, "even", "C")]})
    m2 = sc.merge(v, other)
    assert len(m2["lessons"]) == 3
    assert len({l["id"] for l in m2["lessons"]}) == 3
    with pytest.raises(Exception):
        sc.validate({"pairs": [{"start": "10:00", "end": "09:00"}]})
    with pytest.raises(Exception):
        sc.validate({"lessons": [L(1, 0, 9)]})
    with pytest.raises(Exception):
        sc.validate([1, 2])


def test_store_persistence():
    p = Path(tempfile.mkdtemp()) / "j.json"
    s = sc.Store(p)
    a = s.upsert("lessons", L(None, 0, 1))
    s.upsert("deadlines", {"title": "x", "due": "2026-01-01T10:00", "priority": "low", "subject": "",
                           "notes": "", "done": False})
    s.mark_notified("k1")
    s2 = sc.Store(p)
    assert len(s2.lessons) == 1 and len(s2.deadlines) == 1 and "k1" in s2.notified
    s2.delete("lessons", a["id"])
    assert sc.Store(p).lessons == []
    p.write_text("{broken", encoding="utf-8")
    s3 = sc.Store(p)
    assert s3.lessons == []


def test_subject_color_stable():
    assert sc.subject_color("Fizika") == sc.subject_color(" fizika ")
    assert sc.humanize_minutes(1500) == (1, 1, 0)


def test_default_semester_start():
    assert sc.default_semester_start(date(2026, 11, 27)) == date(2026, 9, 1)
    assert sc.default_semester_start(date(2027, 1, 10)) == date(2026, 9, 1)
    assert sc.default_semester_start(date(2027, 3, 10)) == date(2027, 2, 1)


def test_exports(tmp_path):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from uzkit import app as appmod
    from uzkit.settings import Settings
    appmod.META = appmod.load_meta()
    appmod.SETTINGS = Settings(appmod.META["slug"] + "_test")
    from dars_jadvali import window
    w = window.MainWindow()
    w.store.data = window.demo_data()
    w.refresh_all()
    out = tmp_path / "a.pdf"
    window.export_pdf(w.week, str(out))
    assert out.read_bytes()[:4] == b"%PDF"
    img = w.week._render_image(800, 500)
    assert img.save(str(tmp_path / "a.png"))
    w.close()
