from __future__ import annotations

import json
import os
import random
import secrets
import sqlite3
import string
from collections import Counter
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlencode

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = Path(os.getenv("TEAM_DATABASE_PATH", BASE_DIR / "team_rooms.db"))
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
USE_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))
RECOMMENDER_URL = os.getenv("RECOMMENDER_URL", "http://localhost:8501").rstrip("/")
TIME_SLOTS = ("아침", "점심", "저녁")
MAX_DATE_RANGE_DAYS = 31
MAX_THEME_CHOICES = 5
THEME_ALIASES = {
    "pc방": "PC방",
    "피시방": "PC방",
    "피씨방": "PC방",
}

THEME_DATA = {
    "음식": [
        "한식",
        "중식",
        "일식",
        "양식",
        "고기/구이",
        "치킨",
        "피자",
        "햄버거",
        "분식",
        "뷔페",
        "파인다이닝",
        "카페",
        "디저트",
        "베이커리",
    ],
    "문화/관람": [
        "영화관",
        "공연",
        "미술관",
        "박물관",
        "한강공원",
    ],
    "실내 놀거리": [
        "방탈출카페",
        "보드게임카페",
        "만화카페",
        "PC방",
        "오락실",
        "노래방",
        "사진관",
        "공방/원데이클래스",
        "찜질방",
    ],
    "스포츠/게임": [
        "볼링장",
        "당구장",
        "탁구장",
        "실내클라이밍",
        "스크린야구",
        "스크린골프",
        "롤러스케이트",
    ],
}


app = Flask(__name__)


def load_secret_key() -> str:
    configured = os.getenv("FLASK_SECRET_KEY")
    if configured:
        return configured
    secret_path = BASE_DIR / ".flask_secret"
    if secret_path.exists():
        return secret_path.read_text(encoding="utf-8").strip()
    generated = secrets.token_hex(32)
    secret_path.write_text(generated, encoding="utf-8")
    return generated


app.secret_key = load_secret_key()
app.config["JSON_AS_ASCII"] = False


@contextmanager
def connect_db() -> Iterator[Any]:
    if USE_POSTGRES:
        import psycopg
        from psycopg.rows import dict_row

        connection = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    else:
        DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(DATABASE_PATH)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def execute(db: Any, sql: str, params: tuple[Any, ...] = ()):
    if USE_POSTGRES:
        sql = sql.replace("?", "%s")
    return db.execute(sql, params)


def insert_member(db: Any, room_code: str, name: str, role: str, token: str) -> int:
    sql = """
        INSERT INTO members(room_code, name, role, token, joined_at)
        VALUES (?, ?, ?, ?, ?)
    """
    params = (room_code, name, role, token, now_iso())
    if USE_POSTGRES:
        return int(execute(db, sql + " RETURNING id", params).fetchone()["id"])
    return int(execute(db, sql, params).lastrowid)


def init_db() -> None:
    sqlite_schema = """
            CREATE TABLE IF NOT EXISTS rooms (
                code TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                host_member_id INTEGER,
                date_override_json TEXT,
                theme_override_json TEXT,
                status TEXT NOT NULL DEFAULT 'collecting',
                final_date TEXT,
                final_slot TEXT,
                final_themes_json TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_code TEXT NOT NULL,
                name TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('host', 'member')),
                token TEXT NOT NULL UNIQUE,
                joined_at TEXT NOT NULL,
                FOREIGN KEY(room_code) REFERENCES rooms(code) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS submissions (
                member_id INTEGER PRIMARY KEY,
                address TEXT NOT NULL DEFAULT '',
                date_choices_json TEXT NOT NULL DEFAULT '[]',
                time_choices_json TEXT NOT NULL DEFAULT '[]',
                themes_json TEXT NOT NULL DEFAULT '[]',
                submitted INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT,
                FOREIGN KEY(member_id) REFERENCES members(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS recommendations (
                room_code TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'pending',
                result_json TEXT,
                error_message TEXT,
                started_at TEXT,
                completed_at TEXT,
                FOREIGN KEY(room_code) REFERENCES rooms(code) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_members_room ON members(room_code);
    """
    postgres_schema = sqlite_schema.replace(
        "id INTEGER PRIMARY KEY AUTOINCREMENT",
        "id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY",
    )
    with connect_db() as db:
        if USE_POSTGRES:
            for statement in postgres_schema.split(";"):
                if statement.strip():
                    execute(db, statement)
            execute(
                db,
                "ALTER TABLE submissions ADD COLUMN IF NOT EXISTS time_choices_json TEXT NOT NULL DEFAULT '[]'",
            )
        else:
            db.executescript(sqlite_schema)
            columns = {
                row["name"]
                for row in execute(db, "PRAGMA table_info(submissions)").fetchall()
            }
            if "time_choices_json" not in columns:
                execute(
                    db,
                    "ALTER TABLE submissions ADD COLUMN time_choices_json TEXT NOT NULL DEFAULT '[]'",
                )


init_db()


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def recommendation_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(app.secret_key, salt="meeting-recommendation")


def recommendation_record(room_code: str) -> dict[str, Any]:
    with connect_db() as db:
        row = execute(
            db,
            "SELECT status, result_json, error_message, started_at, completed_at FROM recommendations WHERE room_code = ?",
            (room_code,),
        ).fetchone()
    if not row:
        return {
            "status": "pending",
            "result": None,
            "error": None,
            "started_at": None,
            "completed_at": None,
        }
    return {
        "status": row["status"],
        "result": parse_json(row["result_json"], None),
        "error": row["error_message"],
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
    }


def save_recommendation_state(
    room_code: str,
    status: str,
    *,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    started_at = now_iso() if status == "running" else None
    completed_at = now_iso() if status in {"completed", "error"} else None
    result_json = json.dumps(result, ensure_ascii=False) if result is not None else None
    with connect_db() as db:
        execute(
            db,
            """
            INSERT INTO recommendations(room_code, status, result_json, error_message, started_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(room_code) DO UPDATE SET
                status = excluded.status,
                result_json = excluded.result_json,
                error_message = excluded.error_message,
                started_at = COALESCE(excluded.started_at, recommendations.started_at),
                completed_at = excluded.completed_at
            """,
            (room_code, status, result_json, error, started_at, completed_at),
        )


def parse_json(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


def clean_text(value: Any, limit: int = 100) -> str:
    return " ".join(str(value or "").strip().split())[:limit]


def theme_key(value: Any) -> str:
    return clean_text(value, 50).replace(" ", "").casefold()


def canonical_theme_name(value: Any) -> str:
    cleaned = clean_text(value, 50)
    key = theme_key(cleaned)
    return THEME_ALIASES.get(key, cleaned)


def dedupe_theme_names(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        canonical = canonical_theme_name(value)
        key = theme_key(canonical)
        if not canonical or not key or key in seen:
            continue
        seen.add(key)
        result.append(canonical)
    return result


def submission_date_slots(submission: Any | None) -> set[str]:
    if not submission:
        return set()

    raw_dates = parse_json(submission["date_choices_json"], [])
    try:
        raw_times = parse_json(submission["time_choices_json"], [])
    except (IndexError, KeyError):
        raw_times = []

    combined: set[str] = set()
    plain_dates: set[str] = set()
    for value in raw_dates:
        text = clean_text(value, 40)
        if "|" in text:
            day, slot = text.split("|", 1)
        else:
            day = text
            slot = ""
        try:
            date.fromisoformat(day)
        except ValueError:
            continue
        if slot in TIME_SLOTS:
            combined.add(f"{day}|{slot}")
        else:
            plain_dates.add(day)

    legacy_times = {slot for slot in raw_times if slot in TIME_SLOTS}
    for day in plain_dates:
        for slot in legacy_times:
            combined.add(f"{day}|{slot}")
    return combined


def generate_room_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    with connect_db() as db:
        while True:
            code = "".join(secrets.choice(alphabet) for _ in range(6))
            exists = execute(db, "SELECT 1 FROM rooms WHERE code = ?", (code,)).fetchone()
            if not exists:
                return code


def room_dates(room: Any) -> list[str]:
    start = date.fromisoformat(room["start_date"])
    end = date.fromisoformat(room["end_date"])
    return [(start + timedelta(days=offset)).isoformat() for offset in range((end - start).days + 1)]


def grouped_room_dates(room: Any) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for day_text in room_dates(room):
        day = date.fromisoformat(day_text)
        key = day.strftime("%Y-%m")
        if not groups or groups[-1]["key"] != key:
            groups.append({"key": key, "label": f"{day.year}년 {day.month}월", "dates": []})
        groups[-1]["dates"].append(
            {
                "value": day_text,
                "label": f"{day.month}/{day.day}",
                "weekday": "월화수목금토일"[day.weekday()],
            }
        )
    return groups


def member_session(room_code: str, token: str) -> None:
    session.clear()
    session["room_code"] = room_code
    session["member_token"] = token


def current_context(room_code: str) -> tuple[Any, Any]:
    with connect_db() as db:
        room = execute(db, "SELECT * FROM rooms WHERE code = ?", (room_code,)).fetchone()
        member = execute(
            db,
            "SELECT * FROM members WHERE room_code = ? AND token = ?",
            (room_code, session.get("member_token", "")),
        ).fetchone()
    if not room:
        abort(404)
    if not member or session.get("room_code") != room_code:
        flash("초대코드와 이름을 입력해 방에 다시 입장해 주세요.", "warning")
        raise PermissionError
    return room, member


def room_member_required(view):
    @wraps(view)
    def wrapped(room_code: str, *args, **kwargs):
        try:
            room, member = current_context(room_code)
        except PermissionError:
            return redirect(url_for("home", join_code=room_code))
        return view(room_code, room, member, *args, **kwargs)

    return wrapped


def host_required(view):
    @wraps(view)
    @room_member_required
    def wrapped(room_code: str, room: Any, member: Any, *args, **kwargs):
        if member["role"] != "host":
            abort(403)
        return view(room_code, room, member, *args, **kwargs)

    return wrapped


def fetch_submission(member_id: int) -> Any | None:
    with connect_db() as db:
        return execute(db, "SELECT * FROM submissions WHERE member_id = ?", (member_id,)).fetchone()


def room_members(room_code: str) -> list[dict[str, Any]]:
    with connect_db() as db:
        rows = execute(
            db,
            """
            SELECT m.id, m.name, m.role, m.joined_at,
                   COALESCE(s.submitted, 0) AS submitted,
                   COALESCE(s.address, '') AS address,
                   s.updated_at
            FROM members m
            LEFT JOIN submissions s ON s.member_id = m.id
            WHERE m.room_code = ?
            ORDER BY CASE m.role WHEN 'host' THEN 0 ELSE 1 END, m.joined_at
            """,
            (room_code,),
        ).fetchall()
    return [dict(row) for row in rows]


def all_members_submitted(room_code: str) -> bool:
    members = room_members(room_code)
    return bool(members) and all(bool(member["submitted"]) for member in members)


def render_survey_form(
    room: Any,
    member: Any,
    *,
    address_value: str,
    selected_dates: set[str],
    selected_themes: set[str],
    custom_theme_text: str,
    status_code: int = 200,
):
    return (
        render_template(
            "survey.html",
            room=room,
            member=member,
            date_groups=grouped_room_dates(room),
            time_slots=TIME_SLOTS,
            theme_data=THEME_DATA,
            selected_dates=selected_dates,
            selected_themes=selected_themes,
            custom_theme_text=custom_theme_text,
            address_value=address_value,
            max_theme_choices=MAX_THEME_CHOICES,
            date_override=parse_json(room["date_override_json"], None),
            theme_override=parse_json(room["theme_override_json"], []),
        ),
        status_code,
    )


def ranked_groups(counter: Counter[str], max_rank_groups: int = 3) -> list[dict[str, Any]]:
    score_groups: dict[int, list[str]] = {}
    for item, score in counter.items():
        if score > 0:
            score_groups.setdefault(score, []).append(item)

    groups = []
    for rank, score in enumerate(sorted(score_groups, reverse=True)[:max_rank_groups], start=1):
        groups.append(
            {
                "rank": rank,
                "votes": score,
                "items": sorted(score_groups[score]),
            }
        )
    return groups


def theme_ranked_groups(counter: Counter[str]) -> list[dict[str, Any]]:
    groups = []
    candidate_count = 0
    score_groups: dict[int, list[str]] = {}
    for item, score in counter.items():
        if score > 0:
            score_groups.setdefault(score, []).append(item)

    for rank, score in enumerate(sorted(score_groups, reverse=True), start=1):
        items = sorted(score_groups[score])
        groups.append({"rank": rank, "votes": score, "items": items})
        candidate_count += len(items)
        if candidate_count >= 3:
            break
    return groups


def build_room_results(room_code: str) -> dict[str, Any]:
    with connect_db() as db:
        room = execute(db, "SELECT * FROM rooms WHERE code = ?", (room_code,)).fetchone()
        submissions = execute(
            db,
            """
            SELECT m.name, s.address, s.date_choices_json, s.time_choices_json, s.themes_json
            FROM members m
            JOIN submissions s ON s.member_id = m.id
            WHERE m.room_code = ? AND s.submitted = 1
            ORDER BY m.joined_at
            """,
            (room_code,),
        ).fetchall()

    date_override = parse_json(room["date_override_json"], None)
    theme_override = parse_json(room["theme_override_json"], [])

    if date_override:
        date_groups = [{"rank": 1, "votes": "방장 확정", "items": [date_override["date"]]}]
        date_slot_votes = {
            date_override["date"]: {slot: 0 for slot in TIME_SLOTS}
        }
    else:
        date_votes: Counter[str] = Counter()
        slot_votes_by_date: dict[str, Counter[str]] = {}
        for submission in submissions:
            choices = submission_date_slots(submission)
            selected_days = {choice.split("|", 1)[0] for choice in choices}
            date_votes.update(selected_days)
            for choice in choices:
                day, slot = choice.split("|", 1)
                slot_votes_by_date.setdefault(day, Counter())[slot] += 1
        date_groups = ranked_groups(date_votes, 3)
        date_slot_votes = {
            day: {slot: counter.get(slot, 0) for slot in TIME_SLOTS}
            for day, counter in slot_votes_by_date.items()
        }

    if theme_override:
        normalized_override = dedupe_theme_names(theme_override)
        theme_groups = [
            {"rank": index, "votes": "방장 확정", "items": [theme]}
            for index, theme in enumerate(normalized_override, 1)
        ]
    else:
        theme_votes: Counter[str] = Counter()
        for submission in submissions:
            normalized_votes = set(dedupe_theme_names(parse_json(submission["themes_json"], [])))
            theme_votes.update(normalized_votes)
        theme_groups = theme_ranked_groups(theme_votes)

    eligible_themes = [item for group in theme_groups for item in group["items"]]
    theme_rank_options: list[list[str]] = []
    occupied_slots = 0
    for group in theme_groups:
        if occupied_slots >= 3:
            break
        slots_for_group = min(len(group["items"]), 3 - occupied_slots)
        theme_rank_options.extend([group["items"]] * slots_for_group)
        occupied_slots += len(group["items"])
    return {
        "date_groups": date_groups,
        "date_slot_votes": date_slot_votes,
        "theme_groups": theme_groups,
        "eligible_themes": eligible_themes,
        "theme_rank_options": theme_rank_options,
        "date_override": date_override,
        "theme_override": theme_override,
    }


def build_handoff_payload(room_code: str) -> dict[str, Any] | None:
    with connect_db() as db:
        room = execute(db, "SELECT * FROM rooms WHERE code = ?", (room_code,)).fetchone()
        if not room or room["status"] != "finalized":
            return None
        users = execute(
            db,
            """
            SELECT m.name, s.address
            FROM members m
            JOIN submissions s ON s.member_id = m.id
            WHERE m.room_code = ? AND s.submitted = 1
            ORDER BY m.joined_at
            """,
            (room_code,),
        ).fetchall()

    themes = parse_json(room["final_themes_json"], [])
    results = build_room_results(room_code)
    date_groups = results["date_groups"]
    date_candidates = [
        {
            "date": item,
            "rank": group["rank"],
            "votes": group["votes"] if isinstance(group["votes"], int) else None,
            "time_slot_votes": results["date_slot_votes"].get(
                item,
                {slot: 0 for slot in TIME_SLOTS},
            ),
        }
        for group in date_groups
        for item in group["items"]
    ]
    return {
        "meeting_date": room["final_date"] or None,
        "date_candidates": date_candidates,
        "time_slot_votes": results["date_slot_votes"].get(
            room["final_date"],
            {slot: 0 for slot in TIME_SLOTS},
        ) if room["final_date"] else {},
        "themes": [{"name": theme, "rank": index} for index, theme in enumerate(themes, start=1)],
        "users": [{"name": row["name"], "address": row["address"]} for row in users],
    }


@app.get("/")
def home():
    return render_template("home.html", join_code=clean_text(request.args.get("join_code"), 6).upper())


@app.get("/health")
def health():
    try:
        with connect_db() as db:
            execute(db, "SELECT 1").fetchone()
    except Exception:
        return jsonify({"status": "error", "database": "unavailable"}), 503
    return jsonify({"status": "ok", "database": "postgresql" if USE_POSTGRES else "sqlite"})


@app.post("/rooms")
def create_room():
    host_name = clean_text(request.form.get("host_name"), 30)
    title = clean_text(request.form.get("title"), 80)
    description = clean_text(request.form.get("description"), 300)
    start_date = request.form.get("start_date", "")
    end_date = request.form.get("end_date", "")

    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except ValueError:
        flash("후보 날짜 범위를 올바르게 입력해 주세요.", "error")
        return redirect(url_for("home"))

    if not host_name or not title:
        flash("방장 이름과 방 이름을 입력해 주세요.", "error")
        return redirect(url_for("home"))
    if end < start or (end - start).days >= MAX_DATE_RANGE_DAYS:
        flash(f"후보 날짜는 시작일부터 최대 {MAX_DATE_RANGE_DAYS}일 범위로 설정해 주세요.", "error")
        return redirect(url_for("home"))

    code = generate_room_code()
    token = secrets.token_urlsafe(24)
    with connect_db() as db:
        execute(
            db,
            """
            INSERT INTO rooms(code, title, description, start_date, end_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (code, title, description, start_date, end_date, now_iso()),
        )
        member_id = insert_member(db, code, host_name, "host", token)
        execute(db, "UPDATE rooms SET host_member_id = ? WHERE code = ?", (member_id, code))
        execute(db, "INSERT INTO submissions(member_id) VALUES (?)", (member_id,))

    member_session(code, token)
    return redirect(url_for("room", room_code=code))


@app.post("/join")
def join_room():
    code = clean_text(request.form.get("code"), 6).upper()
    name = clean_text(request.form.get("name"), 30)
    if not code or not name:
        flash("초대코드와 사용자 이름을 입력해 주세요.", "error")
        return redirect(url_for("home", join_code=code))

    with connect_db() as db:
        room = execute(db, "SELECT * FROM rooms WHERE code = ?", (code,)).fetchone()
        if not room:
            flash("존재하지 않는 초대코드입니다.", "error")
            return redirect(url_for("home", join_code=code))
        duplicate = execute(
            db,
            "SELECT 1 FROM members WHERE room_code = ? AND lower(name) = lower(?)",
            (code, name),
        ).fetchone()
        if duplicate:
            flash("방 안에서 이미 사용 중인 이름입니다. 구분되는 이름을 입력해 주세요.", "error")
            return redirect(url_for("home", join_code=code))

        token = secrets.token_urlsafe(24)
        member_id = insert_member(db, code, name, "member", token)
        execute(db, "INSERT INTO submissions(member_id) VALUES (?)", (member_id,))

    member_session(code, token)
    return redirect(url_for("room", room_code=code))


@app.get("/rooms/<room_code>")
@room_member_required
def room(room_code: str, room: Any, member: Any):
    submission = fetch_submission(member["id"])
    final_summary = None
    if room["status"] == "finalized":
        results = build_room_results(room_code)
        final_summary = {
            "date_groups": results["date_groups"],
            "date_slot_votes": results["date_slot_votes"],
            "final_date": room["final_date"],
            "themes": parse_json(room["final_themes_json"], []),
        }
    return render_template(
        "room.html",
        room=room,
        member=member,
        submission=submission,
        members=room_members(room_code),
        all_submitted=all_members_submitted(room_code),
        date_override=parse_json(room["date_override_json"], None),
        theme_override=parse_json(room["theme_override_json"], []),
        handoff=build_handoff_payload(room_code),
        final_summary=final_summary,
        recommendation=recommendation_record(room_code),
        recommender_url=RECOMMENDER_URL,
    )


@app.get("/rooms/<room_code>/survey")
@room_member_required
def survey(room_code: str, room: Any, member: Any):
    submission = fetch_submission(member["id"])
    selected_themes = set(parse_json(submission["themes_json"], [])) if submission else set()
    selected_dates = submission_date_slots(submission)
    known_themes = {theme for values in THEME_DATA.values() for theme in values}
    return render_survey_form(
        room,
        member,
        address_value=submission["address"] if submission else "",
        selected_dates=selected_dates,
        selected_themes=selected_themes,
        custom_theme_text=", ".join(sorted(selected_themes - known_themes)),
    )


@app.post("/rooms/<room_code>/survey")
@room_member_required
def save_survey(room_code: str, room: Any, member: Any):
    address = clean_text(request.form.get("address"), 150)
    valid_dates = set(room_dates(room))
    valid_choices = {
        f"{day}|{slot}"
        for day in valid_dates
        for slot in TIME_SLOTS
    }
    date_choices: set[str] = set()
    plain_dates: set[str] = set()
    for raw_choice in request.form.getlist("date_choices"):
        if "|" in raw_choice:
            if raw_choice in valid_choices:
                date_choices.add(raw_choice)
        else:
            if raw_choice in valid_dates:
                plain_dates.add(raw_choice)

    # 직전 배포 화면에서 전송한 날짜/공통 시간대 형식도 조합형으로 변환한다.
    submitted_times = {
        slot for slot in request.form.getlist("time_choices") if slot in TIME_SLOTS
    }
    for day in plain_dates:
        for slot in submitted_times:
            date_choices.add(f"{day}|{slot}")
    date_choices = sorted(date_choices)

    known_themes = {theme for values in THEME_DATA.values() for theme in values}
    preset_themes = [clean_text(theme, 50) for theme in request.form.getlist("themes")]
    preset_themes = [theme for theme in preset_themes if theme in known_themes]
    custom_theme_text = request.form.get("custom_themes", "")
    custom_themes = [
        clean_text(theme, 50)
        for theme in custom_theme_text.replace("\n", ",").split(",")
        if clean_text(theme, 50)
    ]
    themes = dedupe_theme_names([*preset_themes, *custom_themes])

    def invalid_form(message: str):
        flash(message, "error")
        return render_survey_form(
            room,
            member,
            address_value=address,
            selected_dates=set(date_choices),
            selected_themes=set(preset_themes),
            custom_theme_text=custom_theme_text,
            status_code=400,
        )

    if not address:
        return invalid_form("팀원 2 코드로 전달할 출발 장소를 입력해 주세요.")
    if not parse_json(room["date_override_json"], None) and not date_choices:
        return invalid_form("가능한 날짜와 시간대를 하나 이상 선택해 주세요.")
    if not parse_json(room["theme_override_json"], []) and not themes:
        return invalid_form("원하는 테마를 하나 이상 선택하거나 직접 입력해 주세요.")
    if len(themes) > MAX_THEME_CHOICES:
        return invalid_form(f"테마는 직접 입력을 포함해 최대 {MAX_THEME_CHOICES}개까지 선택할 수 있습니다.")

    with connect_db() as db:
        execute(
            db,
            """
            INSERT INTO submissions(
                member_id, address, date_choices_json, time_choices_json,
                themes_json, submitted, updated_at
            )
            VALUES (?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(member_id) DO UPDATE SET
                address = excluded.address,
                date_choices_json = excluded.date_choices_json,
                time_choices_json = excluded.time_choices_json,
                themes_json = excluded.themes_json,
                submitted = 1,
                updated_at = excluded.updated_at
            """,
            (
                member["id"],
                address,
                json.dumps(date_choices, ensure_ascii=False),
                "[]",
                json.dumps(themes, ensure_ascii=False),
                now_iso(),
            ),
        )
        execute(
            db,
            """
            UPDATE rooms
            SET status = 'collecting', final_date = NULL, final_slot = NULL, final_themes_json = NULL
            WHERE code = ?
            """,
            (room_code,),
        )

    flash("의견 제출이 완료되었습니다. 대기룸에서 언제든 수정할 수 있습니다.", "success")
    return redirect(url_for("room", room_code=room_code))


@app.post("/rooms/<room_code>/host-settings")
@host_required
def host_settings(room_code: str, room: Any, member: Any):
    date_override_json = None
    if request.form.get("date_mode") == "fixed":
        fixed_date = request.form.get("fixed_date", "")
        if fixed_date not in room_dates(room):
            flash("방장이 확정할 날짜를 올바르게 선택해 주세요.", "error")
            return redirect(url_for("room", room_code=room_code))
        date_override_json = json.dumps({"date": fixed_date}, ensure_ascii=False)

    theme_override_json = None
    if request.form.get("theme_mode") == "fixed":
        fixed_themes = [
            clean_text(theme, 50)
            for theme in request.form.get("fixed_themes", "").replace("\n", ",").split(",")
            if clean_text(theme, 50)
        ]
        fixed_themes = dedupe_theme_names(fixed_themes)[:3]
        if not fixed_themes:
            flash("방장이 확정할 테마를 1개 이상 입력해 주세요.", "error")
            return redirect(url_for("room", room_code=room_code))
        theme_override_json = json.dumps(fixed_themes, ensure_ascii=False)

    with connect_db() as db:
        execute(
            db,
            """
            UPDATE rooms
            SET date_override_json = ?, theme_override_json = ?, status = 'collecting',
                final_date = NULL, final_slot = NULL, final_themes_json = NULL
            WHERE code = ?
            """,
            (date_override_json, theme_override_json, room_code),
        )
        rows = execute(
            db,
            """
            SELECT s.member_id, s.address, s.date_choices_json, s.time_choices_json, s.themes_json
            FROM submissions s
            JOIN members m ON m.id = s.member_id
            WHERE m.room_code = ?
            """,
            (room_code,),
        ).fetchall()
        for row in rows:
            has_address = bool(clean_text(row["address"], 150))
            has_date_slots = bool(submission_date_slots(row))
            has_themes = bool(parse_json(row["themes_json"], []))
            remains_complete = (
                has_address
                and (date_override_json is not None or has_date_slots)
                and (theme_override_json is not None or has_themes)
            )
            execute(
                db,
                "UPDATE submissions SET submitted = ? WHERE member_id = ?",
                (1 if remains_complete else 0, row["member_id"]),
            )
    flash("방장 전용 설정을 저장했습니다. 확정한 항목은 조원 투표 대신 사용됩니다.", "success")
    return redirect(url_for("room", room_code=room_code))


@app.get("/rooms/<room_code>/compile")
@host_required
def compile_results(room_code: str, room: Any, member: Any):
    if not all_members_submitted(room_code):
        flash("현재 입장한 인원이 모두 의견을 제출한 뒤 취합할 수 있습니다.", "warning")
        return redirect(url_for("room", room_code=room_code))
    results = build_room_results(room_code)
    return render_template("compile.html", room=room, member=member, results=results)


@app.post("/rooms/<room_code>/compile")
@host_required
def finalize_results(room_code: str, room: Any, member: Any):
    if not all_members_submitted(room_code):
        flash("전원 제출이 완료되지 않았습니다.", "error")
        return redirect(url_for("room", room_code=room_code))

    results = build_room_results(room_code)
    available_dates = {item for group in results["date_groups"] for item in group["items"]}
    selected_date = request.form.get("selected_date", "").strip()
    if selected_date and selected_date not in available_dates:
        flash("선택한 날짜 결과를 확인할 수 없습니다.", "error")
        return redirect(url_for("compile_results", room_code=room_code))

    eligible_themes = results["eligible_themes"]
    ranked_themes = [
        request.form.get(f"ranked_theme_{rank}", "")
        for rank in range(1, 4)
    ]
    submitted_ranked_themes = [theme for theme in ranked_themes if theme]
    if len(submitted_ranked_themes) != len(
        {theme_key(theme) for theme in submitted_ranked_themes}
    ):
        flash("같은 테마를 여러 순위에 중복으로 선택할 수 없습니다.", "error")
        return redirect(url_for("compile_results", room_code=room_code))

    for index, theme in enumerate(ranked_themes):
        if not theme:
            continue
        rank_options = results["theme_rank_options"]
        if index >= len(rank_options) or theme not in rank_options[index]:
            flash(f"{index + 1}순위 테마가 투표 결과의 해당 순위 후보와 맞지 않습니다.", "error")
            return redirect(url_for("compile_results", room_code=room_code))

    final_themes = dedupe_theme_names(
        [theme for theme in ranked_themes if theme in eligible_themes]
    )[:3]

    # 이전 화면 형식으로 제출된 값도 계속 처리한다.
    if not final_themes:
        legacy_themes = [
            theme
            for theme in request.form.getlist("selected_themes")
            if theme in eligible_themes
        ]
        final_themes = dedupe_theme_names(legacy_themes)[:3]
    if not final_themes and len(eligible_themes) <= 3:
        final_themes = eligible_themes

    if not final_themes:
        flash("최종 테마를 1개 이상 선택해 주세요.", "error")
        return redirect(url_for("compile_results", room_code=room_code))

    final_date = selected_date or None
    final_slot = None
    with connect_db() as db:
        execute(
            db,
            """
            UPDATE rooms
            SET status = 'finalized', final_date = ?, final_slot = ?, final_themes_json = ?
            WHERE code = ?
            """,
            (final_date, final_slot, json.dumps(final_themes, ensure_ascii=False), room_code),
        )
        execute(db, "DELETE FROM recommendations WHERE room_code = ?", (room_code,))

    if final_date:
        flash("최종 결과를 확정했습니다. 팀원 2 전달용 JSON도 생성되었습니다.", "success")
    else:
        flash("테마 결과를 확정했습니다. 날짜는 미정 값으로 팀원 2에게 전달됩니다.", "success")
    return redirect(url_for("room", room_code=room_code))


@app.post("/rooms/<room_code>/recommendation/start")
@host_required
def start_recommendation(room_code: str, room: Any, member: Any):
    if room["status"] != "finalized":
        flash("날짜와 테마를 먼저 최종 확정해 주세요.", "warning")
        return redirect(url_for("room", room_code=room_code))
    if not room["final_date"]:
        flash("방장이 최종 날짜를 선택한 뒤 장소 추천을 실행할 수 있습니다.", "warning")
        return redirect(url_for("room", room_code=room_code))

    payload = build_handoff_payload(room_code)
    if not payload or not payload.get("users") or not payload.get("themes"):
        flash("장소 추천에 필요한 참여자 또는 테마 정보가 부족합니다.", "error")
        return redirect(url_for("room", room_code=room_code))

    save_recommendation_state(room_code, "running")
    token = recommendation_serializer().dumps({"room_code": room_code})
    query = urlencode({"room_code": room_code, "run_token": token})
    return redirect(f"{RECOMMENDER_URL}/?{query}")


@app.get("/api/rooms/<room_code>/status")
@room_member_required
def room_status(room_code: str, room: Any, member: Any):
    members = room_members(room_code)
    return jsonify(
        {
            "room_code": room_code,
            "status": room["status"],
            "members": members,
            "all_submitted": bool(members) and all(bool(item["submitted"]) for item in members),
            "current_member_id": member["id"],
            "current_role": member["role"],
            "handoff": build_handoff_payload(room_code),
            "recommendation": recommendation_record(room_code),
        }
    )


@app.get("/api/rooms/<room_code>/handoff")
def room_handoff(room_code: str):
    payload = build_handoff_payload(room_code.upper())
    if payload is None:
        return jsonify({"error": "아직 최종 결과가 확정되지 않았습니다."}), 409
    return jsonify(payload)


@app.get("/handoff")
def compatible_handoff():
    room_code = clean_text(request.args.get("room_code"), 6).upper()
    if not room_code:
        return jsonify({"error": "room_code 쿼리 값이 필요합니다."}), 400
    return room_handoff(room_code)


@app.get("/api/rooms/<room_code>/recommendation")
def recommendation_result(room_code: str):
    room_code = clean_text(room_code, 6).upper()
    with connect_db() as db:
        room = execute(db, "SELECT status FROM rooms WHERE code = ?", (room_code,)).fetchone()
    if not room:
        return jsonify({"error": "방을 찾을 수 없습니다."}), 404
    return jsonify(recommendation_record(room_code))


@app.post("/api/rooms/<room_code>/recommendation")
def save_recommendation_result(room_code: str):
    room_code = clean_text(room_code, 6).upper()
    body = request.get_json(silent=True) or {}
    token = clean_text(body.get("run_token"), 1000)
    try:
        signed = recommendation_serializer().loads(token, max_age=7200)
    except SignatureExpired:
        return jsonify({"error": "추천 실행 토큰이 만료되었습니다."}), 403
    except BadSignature:
        return jsonify({"error": "유효하지 않은 추천 실행 토큰입니다."}), 403
    if signed.get("room_code") != room_code:
        return jsonify({"error": "추천 실행 방 정보가 일치하지 않습니다."}), 403

    status = body.get("status")
    if status == "completed" and isinstance(body.get("result"), dict):
        save_recommendation_state(room_code, "completed", result=body["result"])
    elif status == "error":
        save_recommendation_state(
            room_code,
            "error",
            error=clean_text(body.get("error"), 500) or "추천 실행 중 오류가 발생했습니다.",
        )
    else:
        return jsonify({"error": "저장할 추천 결과 형식이 올바르지 않습니다."}), 400
    return jsonify({"status": "ok"})


@app.post("/rooms/<room_code>/leave")
@room_member_required
def leave_room(room_code: str, room: Any, member: Any):
    if member["role"] == "host":
        flash("방장은 방을 나갈 수 없습니다. 서버를 재시작해도 방 정보는 유지됩니다.", "warning")
        return redirect(url_for("room", room_code=room_code))
    with connect_db() as db:
        execute(db, "DELETE FROM members WHERE id = ?", (member["id"],))
    session.clear()
    flash("방에서 나왔습니다.", "success")
    return redirect(url_for("home"))


@app.post("/rooms/<room_code>/members/<int:member_id>/kick")
@host_required
def kick_member(room_code: str, room: Any, member: Any, member_id: int):
    with connect_db() as db:
        target = execute(
            db,
            "SELECT id, name, role FROM members WHERE id = ? AND room_code = ?",
            (member_id, room_code),
        ).fetchone()
        if not target:
            flash("이미 나갔거나 존재하지 않는 조원입니다.", "warning")
            return redirect(url_for("room", room_code=room_code))
        if target["role"] == "host" or target["id"] == member["id"]:
            flash("방장은 추방할 수 없습니다.", "error")
            return redirect(url_for("room", room_code=room_code))

        execute(db, "DELETE FROM members WHERE id = ?", (member_id,))
        execute(
            db,
            """
            UPDATE rooms
            SET status = 'collecting', final_date = NULL, final_slot = NULL,
                final_themes_json = NULL
            WHERE code = ?
            """,
            (room_code,),
        )
        execute(db, "DELETE FROM recommendations WHERE room_code = ?", (room_code,))

    flash(f"{target['name']} 님을 방에서 내보냈습니다.", "success")
    return redirect(url_for("room", room_code=room_code))


@app.errorhandler(403)
def forbidden(_error):
    return render_template("error.html", message="방장만 사용할 수 있는 기능입니다."), 403


@app.errorhandler(404)
def not_found(_error):
    return render_template("error.html", message="요청한 방이나 페이지를 찾을 수 없습니다."), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
