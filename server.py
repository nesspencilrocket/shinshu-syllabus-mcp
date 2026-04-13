"""信州大学シラバス MCP サーバー

信州大学のシラバスを検索・閲覧できるMCPサーバー。
データソース: campus-3.shinshu-u.ac.jp/syllabusj/（公開シラバスデータ、認証不要）

対応学部:
  人文学部、教育学部、経法学部、理学部、医学部、工学部、農学部、繊維学部、
  共通教育、グローバル化推進センター

対応大学院:
  教育学研究科、総合人文社会科学研究科、医学系研究科、
  総合理工学研究科（理学・工学・繊維学・農学・生命医工学）、
  総合医理工学研究科（医学系・総合理工学・生命医工学）、総合工学系研究科
"""

import json
from pathlib import Path
from collections import Counter

from mcp.server.fastmcp import FastMCP

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

# 学部コード → 名称のマッピング
FACULTY_MAP = {
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

# データキャッシュ
_courses: list[dict] = []


def _load_courses() -> list[dict]:
    """JSONファイルからコースデータを読み込む（初回のみ）。"""
    global _courses
    if _courses:
        return _courses
    for path in sorted(DATA_DIR.glob("courses_*.json"), reverse=True):
        with open(path, encoding="utf-8") as f:
            _courses.extend(json.load(f))
    return _courses


def _match(value: str, query: str) -> bool:
    """大文字小文字を区別しない部分一致検索（日本語・英語対応）。"""
    return query.lower() in value.lower()


def _format_course_summary(course: dict) -> dict:
    """コースの要約情報を返す（一覧表示用）。"""
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
) -> list[dict]:
    """信州大学のシラバスを検索する。

    Args:
        keyword: 科目名・概要・授業計画で検索（例: "プログラミング", "線形代数", "English"）
        instructor: 教員名で検索（例: "山田", "鈴木"）
        faculty: 学部・研究科名で絞り込み（例: "工学部", "理学部", "共通教育", "繊維", "医"）
                 学部コードも使用可: L(人文), E(教育), J(経法), S(理), M(医), T(工), A(農), F(繊維), G(共通教育)
        period: 開講期間で絞り込み（"前期", "後期", "通年"）
        day: 曜日で絞り込み（"月", "火", "水", "木", "金", "土"）
        credits: 単位数で絞り込み（例: "2", "1"）
        target: 対象学生で絞り込み（例: "1年", "2～4", "3年"）
        limit: 最大件数（デフォルト20、最大100）

    Returns:
        マッチしたコースの一覧（要約情報）
    """
    courses = _load_courses()
    limit = min(limit, 100)
    results = []

    for c in courses:
        # キーワード検索（科目名、概要、授業計画、分野）
        if keyword and not any(
            _match(c.get(field, ""), keyword)
            for field in ["title", "overview", "objectives", "plan", "notes"]
        ):
            continue

        # 教員名検索
        if instructor and not (
            _match(c.get("instructor", ""), instructor)
            or _match(c.get("sub_instructor", ""), instructor)
        ):
            continue

        # 学部絞り込み（名称またはコード）
        if faculty:
            faculty_match = (
                _match(c.get("faculty", ""), faculty)
                or _match(c.get("faculty_code", ""), faculty)
                or _match(c.get("faculty_display", ""), faculty)
            )
            if not faculty_match:
                continue

        # 開講期間
        if period and not _match(c.get("period", ""), period):
            continue

        # 曜日
        if day and not _match(c.get("schedule", ""), day):
            continue

        # 単位数
        if credits and not _match(c.get("credits", ""), credits):
            continue

        # 対象学生
        if target and not _match(c.get("target_students", ""), target):
            continue

        results.append(_format_course_summary(c))
        if len(results) >= limit:
            break

    return results


@mcp.tool()
def get_course(course_id: str) -> dict:
    """科目IDで詳細情報を取得する。

    Args:
        course_id: 科目ID（例: "2025_T_TA001"）。search_coursesの結果に含まれるidフィールドを使用する。

    Returns:
        科目の全詳細情報（授業のねらい、概要、授業計画、成績評価方法、教科書等を含む）
    """
    courses = _load_courses()
    for c in courses:
        if c.get("id") == course_id:
            return c
    return {"error": f"科目ID '{course_id}' が見つかりません。search_coursesで検索してIDを確認してください。"}


@mcp.tool()
def get_course_by_code(code: str, faculty_code: str = "", year: int = 0) -> list[dict]:
    """登録コード（科目コード）でシラバスを検索する。

    Args:
        code: 登録コード（例: "TA001", "LH117"）。部分一致で検索する。
        faculty_code: 学部コード（省略可、例: "T", "L"）
        year: 年度（省略時は全年度対象）

    Returns:
        マッチしたコースの一覧
    """
    courses = _load_courses()
    results = []
    for c in courses:
        if not _match(c.get("code", ""), code):
            continue
        if faculty_code and not _match(c.get("faculty_code", ""), faculty_code):
            continue
        if year and c.get("year") != year:
            continue
        results.append(c)
    return results


@mcp.tool()
def list_instructors(keyword: str = "", faculty: str = "") -> list[str]:
    """教員一覧を取得する。キーワードや学部で絞り込み可能。

    Args:
        keyword: 教員名の一部（例: "山田"）。空なら全教員を返す。
        faculty: 学部名・コードで絞り込み（例: "工学部", "T"）

    Returns:
        教員名のリスト（五十音順）
    """
    courses = _load_courses()
    instructors = set()
    for c in courses:
        if faculty and not (
            _match(c.get("faculty", ""), faculty)
            or _match(c.get("faculty_code", ""), faculty)
        ):
            continue
        name = c.get("instructor", "").strip()
        if name:
            # 複数教員が記載されている場合は分割
            for n in re.split(r"[,、／/]", name):
                n = n.strip()
                if n:
                    instructors.add(n)

    result = sorted(instructors)
    if keyword:
        result = [i for i in result if _match(i, keyword)]
    return result


@mcp.tool()
def list_faculties() -> list[dict]:
    """利用可能な学部・研究科の一覧とそのコード、科目数を返す。

    Returns:
        学部・研究科コード、名称、科目数のリスト
    """
    courses = _load_courses()
    counts = Counter(c.get("faculty_code", "不明") for c in courses)

    result = []
    for code, name in FACULTY_MAP.items():
        count = counts.get(code, 0)
        if count > 0:
            result.append({"code": code, "name": name, "course_count": count})

    return result


@mcp.tool()
def course_stats(faculty: str = "") -> dict:
    """シラバスデータの統計情報を返す。

    Args:
        faculty: 学部名・コードで絞り込み（省略時は全学）

    Returns:
        科目数、学期別・学部別・曜日別等の統計情報
    """
    courses = _load_courses()

    if faculty:
        courses = [
            c
            for c in courses
            if _match(c.get("faculty", ""), faculty)
            or _match(c.get("faculty_code", ""), faculty)
        ]

    periods = Counter()
    faculties = Counter()
    schedules = Counter()
    credits_dist = Counter()

    for c in courses:
        periods[c.get("period", "不明")] += 1
        faculties[c.get("faculty", "不明")] += 1

        # 曜日を抽出
        sched = c.get("schedule", "")
        for day in ["月", "火", "水", "木", "金", "土"]:
            if day in sched:
                schedules[day] += 1

        cred = c.get("credits", "不明")
        credits_dist[cred] += 1

    return {
        "total_courses": len(courses),
        "by_period": dict(sorted(periods.items())),
        "by_faculty": dict(sorted(faculties.items(), key=lambda x: -x[1])),
        "by_day": {
            day: schedules.get(day, 0)
            for day in ["月", "火", "水", "木", "金", "土"]
        },
        "by_credits": dict(sorted(credits_dist.items())),
    }


# re モジュールのインポート（list_instructors で使用）
import re

if __name__ == "__main__":
    mcp.run(transport="stdio")
