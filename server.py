"""信州大学シラバス MCP サーバー

信州大学のシラバスを検索・閲覧できるMCPサーバー。
データソース: campus-3.shinshu-u.ac.jp/syllabusj/（公開シラバスデータ）

事前に scraper.py を実行して data/courses_YYYY.json を生成しておく必要があります。
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from collections import Counter
from pathlib import Path
from threading import RLock

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("shinshu_syllabus.server")

DATA_DIR = Path(__file__).parent / "data"

mcp = FastMCP(
    "shinshu-syllabus",
    instructions=(
        "信州大学のシラバスを検索・閲覧できるMCPサーバーです。"
        "科目名・教員名・キーワードで検索したり、学部・曜日・学期で絞り込めます。"
        "信州大学は松本（人文・経法・理・医）、長野（工）、上田（繊維）、"
        "伊那（農）、松本（共通教育/1年次）の各キャンパスに学部があります。"
    ),
)

FACULTY_MAP: dict[str, str] = {
    "L": "人文学部",
    "E": "教育学部",
    "J": "経法学部",
    "S": "理学部",
    "M": "医学部",
    "T": "工学部",
    "A": "農学部",
    "F": "繊維学部",
    "G": "共通教育",
    "R2": "グローバル化推進センター",
    "EA": "教育学研究科",
    "UA": "総合人文社会科学研究科",
    "MS": "医学系研究科（修士課程）",
    "SS": "総合理工学研究科（理学専攻）",
    "TS": "総合理工学研究科（工学専攻）",
    "FS": "総合理工学研究科（繊維学専攻）",
    "AS": "総合理工学研究科（農学専攻）",
    "BS": "総合理工学研究科（生命医工学専攻）",
    "HM": "総合医理工学研究科（医学系専攻）",
    "HS": "総合医理工学研究科（総合理工学専攻）",
    "HB": "総合医理工学研究科（生命医工学専攻）",
    "ST": "総合工学系研究科",
}

# 曜日（土日含む。集中講義の日曜開講に備える）
WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]

# 検索対象キーワードの上限（DoS 防止）
MAX_QUERY_LENGTH = 200


# ---------------------------------------------------------------------------
# データロード
# ---------------------------------------------------------------------------


class CourseStore:
    """JSON ファイルからコースデータを読み込み、メモリにキャッシュする。

    ファイルの mtime を見て、変更があれば自動的にリロードする。
    """

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._lock = RLock()
        self._courses: list[dict] = []
        self._loaded_paths: dict[Path, float] = {}  # path -> mtime

    def _scan_files(self) -> list[Path]:
        if not self._data_dir.exists():
            return []
        return sorted(self._data_dir.glob("courses_*.json"), reverse=True)

    def _needs_reload(self) -> bool:
        files = self._scan_files()
        if {p.resolve() for p in files} != {p.resolve() for p in self._loaded_paths}:
            return True
        return any(p.stat().st_mtime != self._loaded_paths.get(p) for p in files)

    def load(self, force: bool = False) -> list[dict]:
        with self._lock:
            if not force and self._courses and not self._needs_reload():
                return self._courses

            files = self._scan_files()
            if not files:
                # キャッシュは空のままにし、空リストを返す。
                # データ未取得は呼び出し側で検出して案内する。
                self._courses = []
                self._loaded_paths = {}
                return self._courses

            seen: set[str] = set()
            collected: list[dict] = []
            new_paths: dict[Path, float] = {}
            for path in files:
                try:
                    with open(path, encoding="utf-8") as f:
                        data = json.load(f)
                except (OSError, json.JSONDecodeError) as exc:
                    logger.error("%s の読み込みに失敗: %s", path, exc)
                    continue
                new_paths[path] = path.stat().st_mtime
                if not isinstance(data, list):
                    logger.warning("%s はリスト形式ではありません", path)
                    continue
                for c in data:
                    if not isinstance(c, dict):
                        continue
                    cid = c.get("id")
                    if not cid or cid in seen:
                        continue
                    seen.add(cid)
                    collected.append(c)

            self._courses = collected
            self._loaded_paths = new_paths
            logger.info(
                "%d 件のコースを %d ファイルから読み込みました",
                len(collected),
                len(new_paths),
            )
            return self._courses

    def is_empty(self) -> bool:
        return not self.load()


_store = CourseStore(DATA_DIR)


# ---------------------------------------------------------------------------
# 文字列正規化・マッチング
# ---------------------------------------------------------------------------


def _normalize(text: str) -> str:
    """検索用に NFKC 正規化 + 小文字化。

    NFKC により全角英数・半角カナ・互換漢字が統一されるため
    「ｾﾝｹｲﾀﾞｲｽｳ」と「センケイダイスウ」のような表記揺れも吸収できる。
    """
    if not text:
        return ""
    return unicodedata.normalize("NFKC", text).lower()


def _match(value: str | None, query: str) -> bool:
    if not value or not query:
        return False
    return _normalize(query) in _normalize(value)


def _validate_query(value: str, name: str) -> str:
    """検索文字列の長さ・型を検証。"""
    if not isinstance(value, str):
        raise ValueError(f"{name} は文字列で指定してください")
    if len(value) > MAX_QUERY_LENGTH:
        raise ValueError(
            f"{name} が長すぎます（{MAX_QUERY_LENGTH} 文字以内）"
        )
    return value


def _coerce_int(value, name: str, default: int) -> int:
    """LLM が文字列で渡してきた数値もできるだけ受け入れる。"""
    if isinstance(value, bool):  # bool は int より先に判定
        raise ValueError(f"{name} には数値を指定してください")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return int(value.strip())
        except ValueError as exc:
            raise ValueError(f"{name} を整数に変換できません: {value!r}") from exc
    return default


# ---------------------------------------------------------------------------
# 整形
# ---------------------------------------------------------------------------


def _format_summary(course: dict) -> dict:
    return {
        "id": course.get("id", ""),
        "title": course.get("title", ""),
        "instructor": course.get("instructor", ""),
        "faculty": course.get("faculty", ""),
        "period": course.get("period", ""),
        "schedule": course.get("schedule", ""),
        "credits": course.get("credits", ""),
        "location": course.get("location", course.get("classroom", "")),
        "url": course.get("url", ""),
    }


def _empty_data_message() -> dict:
    return {
        "error": (
            "シラバスデータがまだ取得されていません。"
            "scraper.py を実行して data/courses_YYYY.json を生成してください。"
            "例: uv run python scraper.py 2025 --undergrad-only"
        ),
        "data_dir": str(DATA_DIR),
    }


# ---------------------------------------------------------------------------
# MCP ツール
# ---------------------------------------------------------------------------


@mcp.tool()
def search_courses(
    keyword: str = "",
    instructor: str = "",
    faculty: str = "",
    period: str = "",
    day: str = "",
    credits: str = "",
    target: str = "",
    limit: int = 20,
) -> dict:
    """信州大学のシラバスを検索する。

    Args:
        keyword: 科目名・概要・授業計画で検索（例: "プログラミング", "線形代数", "English"）
        instructor: 教員名で検索（例: "山田", "鈴木"）
        faculty: 学部名で絞り込み（例: "工学部", "理学部", "共通教育"）。コードも可: L,E,J,S,M,T,A,F,G
        period: 開講期間で絞り込み（"前期", "後期", "通年"）
        day: 曜日で絞り込み（"月", "火", "水", "木", "金", "土", "日"）
        credits: 単位数で絞り込み（例: "2", "1"）
        target: 対象学生で絞り込み（例: "1年", "2～4"）
        limit: 最大件数（1〜100、デフォルト20）

    Returns:
        {"results": [...], "total_matches": int} 形式の辞書。
        データ未取得時は {"error": "..."} を返す。
    """
    courses = _store.load()
    if not courses:
        return _empty_data_message()

    try:
        keyword = _validate_query(keyword, "keyword")
        instructor = _validate_query(instructor, "instructor")
        faculty = _validate_query(faculty, "faculty")
        period = _validate_query(period, "period")
        day = _validate_query(day, "day")
        credits = _validate_query(credits, "credits")
        target = _validate_query(target, "target")
        limit_value = _coerce_int(limit, "limit", 20)
    except ValueError as exc:
        return {"error": str(exc)}

    # limit を 1〜100 にクランプ
    limit_value = max(1, min(limit_value, 100))

    matched: list[dict] = []
    for c in courses:
        if keyword:
            keyword_fields = ("title", "overview", "objectives", "plan", "notes")
            if not any(_match(c.get(f), keyword) for f in keyword_fields):
                continue
        if instructor and not (
            _match(c.get("instructor"), instructor)
            or _match(c.get("sub_instructor"), instructor)
        ):
            continue
        if faculty and not (
            _match(c.get("faculty"), faculty)
            or _match(c.get("faculty_code"), faculty)
        ):
            continue
        if period and not _match(c.get("period"), period):
            continue
        if day and not _match(c.get("schedule"), day):
            continue
        if credits and not _match(c.get("credits"), credits):
            continue
        if target and not _match(c.get("target_students"), target):
            continue
        matched.append(c)

    truncated = len(matched) > limit_value
    return {
        "results": [_format_summary(c) for c in matched[:limit_value]],
        "total_matches": len(matched),
        "returned": min(len(matched), limit_value),
        "truncated": truncated,
    }


@mcp.tool()
def get_course(course_id: str) -> dict:
    """科目IDで詳細情報を取得する。

    Args:
        course_id: 科目ID（例: "2025_T_T0008200"）。search_coursesの結果のidを使用。
    """
    courses = _store.load()
    if not courses:
        return _empty_data_message()
    if not isinstance(course_id, str) or not course_id.strip():
        return {"error": "course_id を指定してください"}

    for c in courses:
        if c.get("id") == course_id:
            return c
    return {"error": f"科目ID '{course_id}' が見つかりません。"}


@mcp.tool()
def get_course_by_code(code: str, faculty_code: str = "", year: int = 0) -> dict:
    """登録コード（科目コード）で検索する。

    Args:
        code: 登録コード（例: "T0008200"）。部分一致。
        faculty_code: 学部コード（省略可）
        year: 年度（省略時は全年度）

    Returns:
        {"results": [...], "total_matches": int}
    """
    courses = _store.load()
    if not courses:
        return _empty_data_message()

    try:
        code = _validate_query(code, "code")
        faculty_code = _validate_query(faculty_code, "faculty_code")
        year_value = _coerce_int(year, "year", 0)
    except ValueError as exc:
        return {"error": str(exc)}

    if not code.strip():
        return {"error": "code を指定してください"}

    results = []
    for c in courses:
        if not _match(c.get("code"), code):
            continue
        if faculty_code and not _match(c.get("faculty_code"), faculty_code):
            continue
        if year_value and c.get("year") != year_value:
            continue
        results.append(c)

    return {"results": results, "total_matches": len(results)}


@mcp.tool()
def list_instructors(keyword: str = "", faculty: str = "", limit: int = 500) -> dict:
    """教員一覧を取得する。

    Args:
        keyword: 教員名の一部（例: "山田"）
        faculty: 学部名・コードで絞り込み（例: "工学部", "T"）
        limit: 最大件数（1〜2000、デフォルト500）
    """
    courses = _store.load()
    if not courses:
        return _empty_data_message()

    try:
        keyword = _validate_query(keyword, "keyword")
        faculty = _validate_query(faculty, "faculty")
        limit_value = _coerce_int(limit, "limit", 500)
    except ValueError as exc:
        return {"error": str(exc)}

    limit_value = max(1, min(limit_value, 2000))

    instructors: set[str] = set()
    for c in courses:
        if faculty and not (
            _match(c.get("faculty"), faculty)
            or _match(c.get("faculty_code"), faculty)
        ):
            continue
        name = (c.get("instructor") or "").strip()
        if not name:
            continue
        for n in re.split(r"[,、／/／]", name):
            n = n.strip()
            if n:
                instructors.add(n)

    sorted_instructors = sorted(instructors)
    if keyword:
        sorted_instructors = [i for i in sorted_instructors if _match(i, keyword)]

    truncated = len(sorted_instructors) > limit_value
    return {
        "instructors": sorted_instructors[:limit_value],
        "total_matches": len(sorted_instructors),
        "truncated": truncated,
    }


@mcp.tool()
def list_faculties() -> dict:
    """利用可能な学部・研究科の一覧とコード、科目数を返す。"""
    courses = _store.load()
    if not courses:
        return _empty_data_message()

    counts = Counter(c.get("faculty_code", "不明") for c in courses)
    faculties = [
        {"code": code, "name": name, "course_count": counts.get(code, 0)}
        for code, name in FACULTY_MAP.items()
        if counts.get(code, 0) > 0
    ]
    return {"faculties": faculties, "total_courses": len(courses)}


@mcp.tool()
def course_stats(faculty: str = "") -> dict:
    """シラバスデータの統計情報を返す。

    Args:
        faculty: 学部名・コードで絞り込み（省略時は全学）
    """
    courses = _store.load()
    if not courses:
        return _empty_data_message()

    try:
        faculty = _validate_query(faculty, "faculty")
    except ValueError as exc:
        return {"error": str(exc)}

    if faculty:
        courses = [
            c
            for c in courses
            if _match(c.get("faculty"), faculty)
            or _match(c.get("faculty_code"), faculty)
        ]

    periods: Counter = Counter()
    faculties: Counter = Counter()
    schedules: Counter = Counter()
    credits_dist: Counter = Counter()

    for c in courses:
        periods[c.get("period") or "不明"] += 1
        faculties[c.get("faculty") or "不明"] += 1
        schedule = c.get("schedule") or ""
        for d in WEEKDAYS:
            if d in schedule:
                schedules[d] += 1
        credits_dist[c.get("credits") or "不明"] += 1

    return {
        "total_courses": len(courses),
        "by_period": dict(sorted(periods.items())),
        "by_faculty": dict(sorted(faculties.items(), key=lambda x: -x[1])),
        "by_day": {d: schedules.get(d, 0) for d in WEEKDAYS},
        "by_credits": dict(sorted(credits_dist.items())),
    }


# ---------------------------------------------------------------------------
# エントリポイント
# ---------------------------------------------------------------------------


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    # 起動時にデータ存在確認
    if _store.is_empty():
        logger.warning(
            "%s にシラバスデータが見つかりません。"
            "ツール呼び出し時にエラーが返ります。"
            "scraper.py を先に実行してください。",
            DATA_DIR,
        )
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
