"""Jadval mantig'i (interfeyssiz): hafta juftligi, kun darslari, keyingi dars, eslatmalar, JSON saqlash."""
import json
import os
import tempfile
import zlib
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

LESSON_TYPES = ["lecture", "practice", "lab", "seminar"]
WEEK_MODES = ["all", "odd", "even"]
PRIORITIES = ["low", "medium", "high"]

DEFAULT_PAIRS = [("08:30", "09:50"), ("10:00", "11:20"), ("11:30", "12:50"),
                 ("13:30", "14:50"), ("15:00", "16:20"), ("16:30", "17:50")]

SUBJECT_COLORS = ["#2f6fde", "#0f9d76", "#e2641b", "#8e44ad", "#d6336c", "#1098ad", "#c28a00", "#5c940d",
                  "#c92a2a", "#495057", "#a0522d", "#0b7285"]


def default_semester_start(today: date = None) -> date:
    """Kuzgi semestr 1-sentabr, bahorgi semestr 1-fevral (sozlamalarda o'zgartiriladi)."""
    t = today or date.today()
    if t.month >= 9:
        return date(t.year, 9, 1)
    if t.month == 1:
        return date(t.year - 1, 9, 1)
    return date(t.year, 2, 1)


def default_data() -> dict:
    return {
        "version": 1,
        "pairs": [{"start": s, "end": e} for s, e in DEFAULT_PAIRS],
        "days": [0, 1, 2, 3, 4, 5],
        "semester_start": default_semester_start().isoformat(),
        "lessons": [],
        "deadlines": [],
        "next_id": 1,
    }


# --------------------------------------------------------------------------- vaqt yordamchilari
def parse_hm(s: str) -> time:
    h, m = str(s).strip().split(":")
    h, m = int(h), int(m)
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError(s)
    return time(h, m)


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def week_number(semester_start, d: date) -> int:
    """Semestr boshidan boshlab hafta raqami (1 dan). Semestr boshlangan hafta = 1-hafta."""
    s = semester_start if isinstance(semester_start, date) else date.fromisoformat(semester_start)
    n = (monday(d) - monday(s)).days // 7 + 1
    return n


def parity(week_no: int) -> str:
    """Toq hafta: 'odd', juft hafta: 'even'. 0 yoki manfiy haftalar ham to'g'ri hisoblanadi."""
    return "odd" if week_no % 2 == 1 else "even"


def occurs(lesson: dict, d: date, semester_start) -> bool:
    if int(lesson.get("day", -1)) != d.weekday():
        return False
    mode = lesson.get("week", "all")
    return mode == "all" or mode == parity(week_number(semester_start, d))


def lessons_on(lessons: Sequence[dict], d: date, semester_start) -> List[dict]:
    return sorted((l for l in lessons if occurs(l, d, semester_start)), key=lambda l: int(l.get("pair", 0)))


def lessons_in_week(lessons: Sequence[dict], week_monday: date, semester_start) -> List[dict]:
    out = []
    for i in range(7):
        out += lessons_on(lessons, week_monday + timedelta(days=i), semester_start)
    return out


def pair_span(pairs: Sequence[dict], pair_no: int, d: date) -> Optional[Tuple[datetime, datetime]]:
    """pair_no 1 dan boshlanadi."""
    if not 1 <= pair_no <= len(pairs):
        return None
    p = pairs[pair_no - 1]
    return datetime.combine(d, parse_hm(p["start"])), datetime.combine(d, parse_hm(p["end"]))


def next_class(lessons, pairs, now: datetime, semester_start, horizon_days: int = 14):
    """Hozir davom etayotgan yoki eng yaqin dars: (dars, boshlanish, tugash, davom_etyaptimi)."""
    for k in range(horizon_days + 1):
        d = now.date() + timedelta(days=k)
        for l in lessons_on(lessons, d, semester_start):
            span = pair_span(pairs, int(l["pair"]), d)
            if not span:
                continue
            st, en = span
            if en <= now:
                continue
            return l, st, en, st <= now < en
    return None


def class_notifications(lessons, pairs, now: datetime, semester_start, minutes: int, notified) -> List[tuple]:
    """Boshlanishiga `minutes` daqiqa yoki kamroq qolgan (hali boshlanmagan) darslar."""
    out = []
    for l in lessons_on(lessons, now.date(), semester_start):
        span = pair_span(pairs, int(l["pair"]), now.date())
        if not span:
            continue
        st = span[0]
        left = (st - now).total_seconds() / 60
        if 0 <= left <= minutes:
            key = f"L{l['id']}:{st.isoformat(timespec='minutes')}"
            if key not in notified:
                out.append((key, l, st))
    return out


def deadline_notifications(deadlines, now: datetime, offsets_min: Sequence[int], notified) -> List[tuple]:
    """Bajarilmagan vazifalar uchun: eng yaqin yetib kelingan chegara (masalan 1440, 60 daqiqa) bo'yicha bitta
    eslatma; muddat o'tgach (24 soat ichida) bitta 'over' eslatma."""
    offs = sorted({int(o) for o in offsets_min if int(o) > 0})
    out = []
    for dl in deadlines:
        if dl.get("done"):
            continue
        try:
            due = datetime.fromisoformat(dl["due"])
        except Exception:
            continue
        left = (due - now).total_seconds() / 60
        if left < 0:
            if left < -24 * 60:
                continue
            tag = "over"
        else:
            cands = [o for o in offs if o >= left]
            if not cands:
                continue
            tag = f"m{min(cands)}"
        key = f"D{dl['id']}:{dl['due']}:{tag}"
        if key not in notified:
            out.append((key, dl, left))
    return out


def deadline_state(dl: dict, now: datetime) -> str:
    if dl.get("done"):
        return "done"
    try:
        due = datetime.fromisoformat(dl["due"])
    except Exception:
        return "active"
    return "overdue" if due < now else "active"


def filter_deadlines(deadlines, mode: str, now: datetime) -> List[dict]:
    """mode: active | done | overdue | all. Tartib: muddat bo'yicha, keyin muhimlik."""
    pr = {p: i for i, p in enumerate(reversed(PRIORITIES))}
    if mode == "all":
        res = list(deadlines)
    elif mode == "active":
        res = [d for d in deadlines if not d.get("done")]
    else:
        res = [d for d in deadlines if deadline_state(d, now) == mode]
    return sorted(res, key=lambda d: (bool(d.get("done")), d.get("due", ""), pr.get(d.get("priority"), 9)))


def subject_color(subject: str) -> str:
    h = zlib.crc32(subject.strip().lower().encode("utf-8"))
    return SUBJECT_COLORS[h % len(SUBJECT_COLORS)]


def humanize_minutes(m: float) -> Tuple[int, int, int]:
    m = max(0, int(m))
    return m // 1440, (m % 1440) // 60, m % 60


# --------------------------------------------------------------------------- import / tekshirish
def validate(data: dict) -> dict:
    """Import qilingan JSON ni tekshiradi va to'g'rilangan nusxasini qaytaradi. Xato bo'lsa ValueError."""
    if not isinstance(data, dict):
        raise ValueError("root")
    out = default_data()
    pairs = data.get("pairs", out["pairs"])
    if not isinstance(pairs, list) or not pairs:
        raise ValueError("pairs")
    norm_pairs = []
    for p in pairs:
        s, e = parse_hm(p["start"]), parse_hm(p["end"])
        if e <= s:
            raise ValueError("pair order")
        norm_pairs.append({"start": s.strftime("%H:%M"), "end": e.strftime("%H:%M")})
    out["pairs"] = norm_pairs
    days = data.get("days", out["days"])
    out["days"] = sorted({int(x) for x in days if 0 <= int(x) <= 6}) or out["days"]
    if data.get("semester_start"):
        out["semester_start"] = date.fromisoformat(str(data["semester_start"])[:10]).isoformat()
    nid = 1
    for l in data.get("lessons", []):
        if not str(l.get("subject", "")).strip():
            raise ValueError("lesson subject")
        day, pair = int(l["day"]), int(l["pair"])
        if not (0 <= day <= 6 and 1 <= pair <= len(norm_pairs)):
            raise ValueError("lesson slot")
        out["lessons"].append({
            "id": nid, "subject": str(l["subject"]).strip(),
            "type": l.get("type") if l.get("type") in LESSON_TYPES else "lecture",
            "group": str(l.get("group", "")), "room": str(l.get("room", "")), "notes": str(l.get("notes", "")),
            "day": day, "pair": pair, "week": l.get("week") if l.get("week") in WEEK_MODES else "all",
            "color": str(l.get("color", "")),
        })
        nid += 1
    for d in data.get("deadlines", []):
        if not str(d.get("title", "")).strip():
            raise ValueError("deadline title")
        due = datetime.fromisoformat(str(d["due"])).isoformat(timespec="minutes")
        out["deadlines"].append({
            "id": nid, "title": str(d["title"]).strip(), "due": due,
            "priority": d.get("priority") if d.get("priority") in PRIORITIES else "medium",
            "subject": str(d.get("subject", "")), "notes": str(d.get("notes", "")), "done": bool(d.get("done")),
        })
        nid += 1
    out["next_id"] = nid
    return out


def merge(base: dict, extra: dict) -> dict:
    """Import qilingan darslar va vazifalarni mavjudlariga qo'shadi (yangi id bilan, takrorlarsiz)."""
    res = json.loads(json.dumps(base))
    nid = int(res.get("next_id", 1))
    have_l = {(l["subject"], l["day"], l["pair"], l["week"], l.get("group", "")) for l in res["lessons"]}
    for l in extra.get("lessons", []):
        k = (l["subject"], l["day"], l["pair"], l["week"], l.get("group", ""))
        if k in have_l:
            continue
        res["lessons"].append({**l, "id": nid})
        have_l.add(k)
        nid += 1
    have_d = {(d["title"], d["due"]) for d in res["deadlines"]}
    for d in extra.get("deadlines", []):
        if (d["title"], d["due"]) in have_d:
            continue
        res["deadlines"].append({**d, "id": nid})
        nid += 1
    res["next_id"] = nid
    return res


# --------------------------------------------------------------------------- saqlash
class Store:
    """jadval.json: darslar, para vaqtlari, vazifalar. Atomik yozish."""

    def __init__(self, path):
        self.path = Path(path)
        self.notified_path = self.path.with_name("notified.json")
        self.data = default_data()
        self.notified = set()
        self.load()

    def load(self):
        try:
            if self.path.exists():
                self.data = validate(json.loads(self.path.read_text(encoding="utf-8")))
        except Exception:
            try:
                self.path.replace(self.path.with_suffix(".broken.json"))
            except Exception:
                pass
            self.data = default_data()
        try:
            if self.notified_path.exists():
                self.notified = set(json.loads(self.notified_path.read_text(encoding="utf-8")))
        except Exception:
            self.notified = set()

    def _write(self, p: Path, obj):
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)

    def save(self):
        self._write(self.path, self.data)

    def mark_notified(self, key: str):
        self.notified.add(key)
        keep = sorted(self.notified)[-3000:]
        self.notified = set(keep)
        self._write(self.notified_path, keep)

    def new_id(self) -> int:
        i = int(self.data.get("next_id", 1))
        self.data["next_id"] = i + 1
        return i

    # --- darslar
    @property
    def lessons(self) -> List[dict]:
        return self.data["lessons"]

    @property
    def deadlines(self) -> List[dict]:
        return self.data["deadlines"]

    @property
    def pairs(self) -> List[dict]:
        return self.data["pairs"]

    @property
    def semester_start(self) -> date:
        return date.fromisoformat(self.data["semester_start"])

    def upsert(self, kind: str, obj: dict) -> dict:
        coll = self.data[kind]
        if obj.get("id"):
            for i, o in enumerate(coll):
                if o["id"] == obj["id"]:
                    coll[i] = obj
                    self.save()
                    return obj
        obj["id"] = self.new_id()
        coll.append(obj)
        self.save()
        return obj

    def delete(self, kind: str, oid: int):
        self.data[kind] = [o for o in self.data[kind] if o["id"] != oid]
        self.save()

    def get(self, kind: str, oid: int) -> Optional[dict]:
        for o in self.data[kind]:
            if o["id"] == oid:
                return o
        return None

    def color_of(self, lesson_or_subject) -> str:
        """Darsning rangi: qo'lda berilgan yoki fanlar ro'yxatidagi tartib bo'yicha takrorlanmas rang."""
        if isinstance(lesson_or_subject, dict):
            if lesson_or_subject.get("color"):
                return lesson_or_subject["color"]
            subject = lesson_or_subject.get("subject", "")
        else:
            subject = lesson_or_subject
        subs = sorted({l["subject"].strip().lower() for l in self.lessons})
        key = subject.strip().lower()
        if key in subs:
            return SUBJECT_COLORS[subs.index(key) % len(SUBJECT_COLORS)]
        return subject_color(subject)

    def subjects(self) -> List[str]:
        return sorted({l["subject"] for l in self.lessons} | {d["subject"] for d in self.deadlines if d["subject"]})
