"""信州大学シラバススクレイパー - campus-3.shinshu-u.ac.jp からシラバスデータを取得

信州大学シラバス検索システムのHTML構造:

検索ページ: /syllabusj/Search?Code={学部コード}
  - フォーム: 開講年度、開講期間、曜日、時限、授業名、教員氏名等で検索
  - 検索結果: テーブル形式で一覧表示

詳細ページ: /syllabusj/Display?BUKYOKU={学部コード}&CODE={科目コード}&NENDO={年度}
  - テーブル形式で詳細情報を表示
  - 項目: 授業名、担当教員、講義期間、曜日・時限、講義室、単位数、
          対象学生、授業のねらい、授業の概要、授業計画、成績評価、
          履修上の注意、教科書、参考書 等

学部コード:
  L: 人文学部, E: 教育学部, J: 経法学部, S: 理学部,
  M: 医学部, T: 工学部, A: 農学部, F: 繊維学部,
  G: 共通教育, R2: グローバル化推進センター

大学院コード:
  EA: 教育学研究科, UA: 総合人文社会科学研究科,
  MS: 医学系研究科(修士), SS: 総合理工学研究科(理学),
  TS: 総合理工学研究科(工学), FS: 総合理工学研究科(繊維学),
  AS: 総合理工学研究科(農学), BS: 総合理工学研究科(生命医工学),
  HM: 総合医理工学研究科(医学系), HS: 総合医理工学研究科(総合理工学),
  HB: 総合医理工学研究科(生命医工学), ST: 総合工学系研究科,
  INKYOUTSUU: 大学院共通教育用科目
"""

import json
import time
import sys
import re
from pathlib import Path
from urllib.parse import urljoin, urlencode

import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://campus-3.shinshu-u.ac.jp/syllabusj"
SEARCH_URL = f"{BASE_URL}/Search"
DISPLAY_URL = f"{BASE_URL}/Display"

# 学部・研究科コードマッピング
FACULTY_CODES = {
    # 学部
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
    # 大学院
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

# 学部コードのみ（大学院を含まない）
UNDERGRADUATE_CODES = ["L", "E", "J", "S", "M", "T", "A", "F", "G", "R2"]

# 全コード
ALL_CODES = list(FACULTY_CODES.keys())


def fetch_search_results(
    client: httpx.Client,
    faculty_code: str,
    year: int,
    period: str = "",
    day: str = "",
    course_name: str = "",
    instructor: str = "",
) -> BeautifulSoup:
    """検索結果ページを取得する。

    信州大学のシラバス検索はGETパラメータでフォームを送信する形式。
    フォームのaction先やパラメータ名はサイトの実装に依存するため、
    直接検索ページにアクセスして結果を取得する。
    """
    params = {"Code": faculty_code}
    if year:
        params["ESSION"] = str(year)  # 年度パラメータ名（サイト固有）

    resp = client.get(SEARCH_URL, params=params)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "lxml")


def parse_search_results(soup: BeautifulSoup, faculty_code: str) -> list[dict]:
    """検索結果テーブルからコース一覧を解析する。

    テーブルのカラム:
    開講年度 | 開講期間 | コード | 授業名 | 教員氏名 | 曜日・時限 | 開講部局 | 開講場所 | ダウンロード
    """
    courses = []

    # テーブルの行を探す
    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 7:
                continue

            # リンクから詳細ページのパラメータを取得
            link = row.find("a", href=True)
            if not link or "Display" not in link.get("href", ""):
                continue

            href = link["href"]
            # Display?BUKYOKU=T&CODE=XXXX&NENDO=2025 のようなURLを解析
            code_match = re.search(r"CODE=([^&]+)", href)
            nendo_match = re.search(r"NENDO=(\d+)", href)
            bukyoku_match = re.search(r"BUKYOKU=([^&]+)", href)

            if not code_match:
                continue

            course_code = code_match.group(1)
            year = int(nendo_match.group(1)) if nendo_match else 0
            bukyoku = bukyoku_match.group(1) if bukyoku_match else faculty_code

            # テーブルのセルからデータ取得
            cell_texts = [c.get_text(strip=True) for c in cells]

            course = {
                "id": f"{year}_{bukyoku}_{course_code}",
                "code": course_code,
                "faculty_code": bukyoku,
                "faculty": FACULTY_CODES.get(bukyoku, bukyoku),
                "year": year,
                "url": urljoin(BASE_URL + "/", href),
            }

            # セルの数に応じてデータをマッピング
            if len(cell_texts) >= 8:
                course["year_display"] = cell_texts[0]
                course["period"] = cell_texts[1]
                course["title"] = cell_texts[3] if cell_texts[3] else link.get_text(strip=True)
                course["instructor"] = cell_texts[4]
                course["schedule"] = cell_texts[5]
                course["faculty_display"] = cell_texts[6]
                course["location"] = cell_texts[7]
            else:
                course["title"] = link.get_text(strip=True)

            if course.get("title"):
                courses.append(course)

    return courses


def fetch_course_detail(
    client: httpx.Client, bukyoku: str, code: str, year: int
) -> dict:
    """シラバス詳細ページからデータを取得する。"""
    params = {"BUKYOKU": bukyoku, "CODE": code, "NENDO": year}
    resp = client.get(DISPLAY_URL, params=params)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    return parse_course_detail(soup, bukyoku, code, year)


def parse_course_detail(
    soup: BeautifulSoup, bukyoku: str, code: str, year: int
) -> dict:
    """シラバス詳細ページのHTMLを解析する。

    構造例:
    | 開講年度 | 2025年度 | 登録コード | XXXX | ... |
    | 授業名   | YYYY     |            |      |     |
    | 担当教員 | ZZZZ     | 副担当     | ...  |     |
    | 講義期間 | 前期     | 曜日・時限 | 月1  | ... |
    ...
    | (1)授業のねらい | テキスト... |
    | (2)授業の概要   | テキスト... |
    ...
    """
    detail = {
        "id": f"{year}_{bukyoku}_{code}",
        "code": code,
        "faculty_code": bukyoku,
        "faculty": FACULTY_CODES.get(bukyoku, bukyoku),
        "year": year,
        "url": f"{DISPLAY_URL}?BUKYOKU={bukyoku}&CODE={code}&NENDO={year}",
    }

    # テーブルの全行を走査してキーバリューペアを抽出
    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue

            # dt/dd パターンやキーバリューテーブルを処理
            i = 0
            while i < len(cells) - 1:
                key = cells[i].get_text(strip=True)
                value = cells[i + 1].get_text(strip=True)

                if key and value:
                    _map_field(detail, key, value)

                i += 2

    # 注意書き等の補足テキストも取得
    # hr タグ以降のテーブルにシラバス本文がある
    hr = soup.find("hr")
    if hr:
        content_table = hr.find_next("table")
        if content_table:
            for row in content_table.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) >= 2:
                    key = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)
                    if key and value:
                        _map_field(detail, key, value)

    return detail


# フィールドマッピング
FIELD_MAP = {
    "授業名": "title",
    "開講年度": "year_display",
    "登録コード": "registration_code",
    "担当教員": "instructor",
    "副担当": "sub_instructor",
    "講義期間": "period",
    "曜日・時限": "schedule",
    "講義室": "classroom",
    "単位数": "credits",
    "対象学生": "target_students",
    "授業形態": "class_type",
    "備考": "notes",
    "(1)授業のねらい": "objectives",
    "(2)授業の概要": "overview",
    "(3)授業計画": "plan",
    "(4)成績評価の方法": "evaluation",
    "(5)履修上の注意": "prerequisites",
    "(6)質問、相談への対応": "consultation",
    "【教科書】": "textbook",
    "【参考書】": "references",
    "【添付ファイル】": "attachments",
    "県内大学開放授業": "open_course_prefectural",
    "市民開放授業": "open_course_public",
}


def _map_field(detail: dict, key: str, value: str):
    """キーに基づいてフィールドをマッピングする。"""
    # 完全一致
    if key in FIELD_MAP:
        detail[FIELD_MAP[key]] = value
        return

    # 部分一致
    for k, v in FIELD_MAP.items():
        if k in key:
            detail[v] = value
            return


def scrape_faculty(
    client: httpx.Client,
    faculty_code: str,
    year: int,
    fetch_details: bool = True,
    delay: float = 0.3,
) -> list[dict]:
    """指定学部の全シラバスをスクレイピングする。"""
    faculty_name = FACULTY_CODES.get(faculty_code, faculty_code)
    print(f"\n--- {faculty_name} ({faculty_code}) を取得中 ---")

    # 検索結果を取得
    soup = fetch_search_results(client, faculty_code, year)
    courses = parse_search_results(soup, faculty_code)
    print(f"  一覧: {len(courses)} 件")

    if not fetch_details:
        return courses

    # 各コースの詳細を取得
    detailed_courses = []
    for i, course in enumerate(courses):
        time.sleep(delay)
        if (i + 1) % 20 == 0 or (i + 1) == len(courses):
            print(f"  詳細取得中: {i + 1}/{len(courses)}")
        try:
            detail = fetch_course_detail(
                client,
                course.get("faculty_code", faculty_code),
                course["code"],
                course.get("year", year),
            )
            # 一覧情報とマージ（詳細ページの情報を優先）
            merged = {**course, **detail}
            detailed_courses.append(merged)
        except Exception as e:
            print(f"  エラー（{course.get('title', course['code'])}）: {e}")
            detailed_courses.append(course)

    return detailed_courses


def scrape_all(
    year: int,
    codes: list[str] | None = None,
    fetch_details: bool = True,
    delay: float = 0.3,
) -> list[dict]:
    """全学部のシラバスをスクレイピングする。"""
    if codes is None:
        codes = ALL_CODES

    all_courses = []
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        for code in codes:
            try:
                courses = scrape_faculty(
                    client, code, year, fetch_details=fetch_details, delay=delay
                )
                all_courses.extend(courses)
            except Exception as e:
                print(f"  学部 {code} でエラー: {e}")
                continue

    return all_courses


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="信州大学シラバススクレイパー",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 2025年度の全学部をスクレイピング
  python scraper.py 2025

  # 工学部と理学部のみ
  python scraper.py 2025 --faculties T S

  # 学部のみ（大学院を除く）
  python scraper.py 2025 --undergrad-only

  # 一覧のみ取得（詳細ページは取得しない）
  python scraper.py 2025 --no-details

  # 複数年度
  python scraper.py 2024 2025

学部コード一覧:
  L: 人文学部, E: 教育学部, J: 経法学部, S: 理学部,
  M: 医学部, T: 工学部, A: 農学部, F: 繊維学部,
  G: 共通教育, R2: グローバル化推進センター
        """,
    )
    parser.add_argument("years", type=int, nargs="+", help="取得する年度（西暦）")
    parser.add_argument(
        "--faculties",
        nargs="*",
        default=None,
        help="取得する学部コード（省略時は全学部）",
    )
    parser.add_argument(
        "--undergrad-only",
        action="store_true",
        help="学部のみ取得（大学院を除く）",
    )
    parser.add_argument(
        "--no-details",
        action="store_true",
        help="詳細ページは取得せず一覧のみ取得",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.3,
        help="リクエスト間の待機時間（秒、デフォルト: 0.3）",
    )

    args = parser.parse_args()

    codes = args.faculties
    if codes is None:
        codes = UNDERGRADUATE_CODES if args.undergrad_only else ALL_CODES

    output_dir = Path("data")
    output_dir.mkdir(exist_ok=True)

    for year in args.years:
        print(f"\n{'='*50}")
        print(f" {year}年度 シラバス取得開始")
        print(f"{'='*50}")

        courses = scrape_all(
            year,
            codes=codes,
            fetch_details=not args.no_details,
            delay=args.delay,
        )

        output_path = output_dir / f"courses_{year}.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(courses, f, ensure_ascii=False, indent=2)

        print(f"\n{len(courses)} 件を {output_path} に保存しました")


if __name__ == "__main__":
    main()
