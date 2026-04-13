"""信州大学シラバススクレイパー - campus-3.shinshu-u.ac.jp からシラバスデータを取得

ページネーション仕組み（実調査に基づく）:
- 検索はPOSTリクエスト
- 1ページ目: BtKENSAKU ボタンで検索実行 (StartNo=0)
- 2ページ目以降: BtNEXT ボタン + サーバーが返す StartNo の値を送信
- 1ページあたり100件表示
- Pos は常に空（未使用）
"""

import json
import time
import re
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://campus-3.shinshu-u.ac.jp/syllabusj"
SEARCH_URL = f"{BASE_URL}/Search"
DISPLAY_URL = f"{BASE_URL}/Display"

FACULTY_CODES = {
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

UNDERGRADUATE_CODES = ["L", "E", "J", "S", "M", "T", "A", "F", "G", "R2"]
ALL_CODES = list(FACULTY_CODES.keys())


def get_hidden_value(soup: BeautifulSoup, name: str) -> str:
    """hidden input の値を取得する。"""
    inp = soup.find("input", {"name": name})
    return inp.get("value", "") if inp else ""


def has_next_button(soup: BeautifulSoup) -> bool:
    """「次へ」ボタンがあるか。"""
    return any(inp.get("name") == "BtNEXT" for inp in soup.find_all("input"))


def get_total_count(soup: BeautifulSoup) -> int | None:
    """「全XXX件中」から総件数を取得。"""
    match = re.search(r'全(\d+)件', soup.get_text())
    return int(match.group(1)) if match else None


def make_base_data(faculty_code: str, year: int) -> dict:
    """共通のフォームデータ。"""
    return {
        "Pos": "",
        "Mode": "1",
        "Bukyoku": faculty_code,
        "Nendo": str(year),
        "Meisyou": "",
        "Kyouin": "",
        "KyouinKana": "",
        "Keikaku": "",
        "Taisyou": "",
        "CodeStart": "",
        "CodeJyouken": "0",
    }


def parse_search_results(soup: BeautifulSoup, faculty_code: str) -> list[dict]:
    """検索結果テーブルからコース一覧を解析する。"""
    courses = []
    seen = set()

    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        if "Display" not in href:
            continue

        code_match = re.search(r"CODE=([^&]+)", href)
        nendo_match = re.search(r"NENDO=(\d+)", href)
        bukyoku_match = re.search(r"BUKYOKU=([^&]+)", href)
        if not code_match:
            continue

        course_code = code_match.group(1)
        year = int(nendo_match.group(1)) if nendo_match else 0
        bukyoku = bukyoku_match.group(1) if bukyoku_match else faculty_code
        cid = f"{year}_{bukyoku}_{course_code}"

        if cid in seen:
            continue
        seen.add(cid)

        row = link.find_parent("tr")
        if not row:
            continue

        cells = row.find_all("td")
        cell_texts = [c.get_text(strip=True) for c in cells]

        course = {
            "id": cid,
            "code": course_code,
            "faculty_code": bukyoku,
            "faculty": FACULTY_CODES.get(bukyoku, bukyoku),
            "year": year,
            "url": f"{BASE_URL}/{href}" if not href.startswith("http") else href,
        }

        if len(cell_texts) >= 8:
            course["year_display"] = cell_texts[0]
            course["period"] = cell_texts[1]
            course["title"] = cell_texts[3] or link.get_text(strip=True)
            course["instructor"] = cell_texts[4]
            course["schedule"] = cell_texts[5]
            course["faculty_display"] = cell_texts[6]
            course["location"] = cell_texts[7]
        else:
            course["title"] = link.get_text(strip=True)

        if course.get("title"):
            courses.append(course)

    return courses


def fetch_course_detail(client: httpx.Client, bukyoku: str, code: str, year: int) -> dict:
    """シラバス詳細ページからデータを取得する。"""
    resp = client.get(DISPLAY_URL, params={"BUKYOKU": bukyoku, "CODE": code, "NENDO": year})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    detail = {
        "id": f"{year}_{bukyoku}_{code}",
        "code": code,
        "faculty_code": bukyoku,
        "faculty": FACULTY_CODES.get(bukyoku, bukyoku),
        "year": year,
        "url": f"{DISPLAY_URL}?BUKYOKU={bukyoku}&CODE={code}&NENDO={year}",
    }

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            i = 0
            while i < len(cells) - 1:
                key = cells[i].get_text(strip=True)
                value = cells[i + 1].get_text(strip=True)
                if key and value:
                    _map_field(detail, key, value)
                i += 2

    return detail


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
}


def _map_field(detail: dict, key: str, value: str):
    if key in FIELD_MAP:
        detail[FIELD_MAP[key]] = value
        return
    for k, v in FIELD_MAP.items():
        if k in key:
            detail[v] = value
            return


def scrape_faculty(
    client: httpx.Client,
    faculty_code: str,
    year: int,
    fetch_details: bool = True,
    delay: float = 0.5,
) -> list[dict]:
    """指定学部の全シラバスをスクレイピングする。"""
    faculty_name = FACULTY_CODES.get(faculty_code, faculty_code)
    print(f"\n--- {faculty_name} ({faculty_code}) を取得中 ---")

    all_courses = []
    seen_ids = set()

    # ページ1: 検索実行
    print(f"  ページ 1...")
    data = make_base_data(faculty_code, year)
    data["StartNo"] = "0"
    data["BtKENSAKU"] = "\u3000\u691c\u3000\u7d22\u3000"

    resp = client.post(SEARCH_URL, params={"Code": faculty_code}, data=data)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    total = get_total_count(soup)
    if total is not None:
        print(f"  全 {total} 件")

    courses = parse_search_results(soup, faculty_code)
    for c in courses:
        if c["id"] not in seen_ids:
            seen_ids.add(c["id"])
            all_courses.append(c)
    print(f"    -> {len(courses)} 件取得 (累計: {len(all_courses)})")

    # ページ2以降: 次へボタン + StartNoをサーバーから取得
    page = 2
    while has_next_button(soup):
        time.sleep(delay)
        start_no = get_hidden_value(soup, "StartNo")
        print(f"  ページ {page} (StartNo={start_no})...")

        data = make_base_data(faculty_code, year)
        data["StartNo"] = start_no
        data["BtNEXT"] = "\u6b21\u3078 >"

        resp = client.post(SEARCH_URL, params={"Code": faculty_code}, data=data)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        courses = parse_search_results(soup, faculty_code)
        new_count = 0
        for c in courses:
            if c["id"] not in seen_ids:
                seen_ids.add(c["id"])
                all_courses.append(c)
                new_count += 1

        print(f"    -> {len(courses)} 件取得 (新規: {new_count}, 累計: {len(all_courses)})")

        if new_count == 0:
            print(f"  新規0件のため終了")
            break

        page += 1

    print(f"  一覧合計: {len(all_courses)} 件")

    if not fetch_details:
        return all_courses

    # 詳細取得
    detailed = []
    for i, course in enumerate(all_courses):
        time.sleep(delay)
        if (i + 1) % 50 == 0 or (i + 1) == len(all_courses):
            print(f"  詳細取得中: {i + 1}/{len(all_courses)}")
        try:
            detail = fetch_course_detail(
                client, course["faculty_code"], course["code"], course.get("year", year)
            )
            detailed.append({**course, **detail})
        except Exception as e:
            print(f"  エラー（{course.get('title', course['code'])}）: {e}")
            detailed.append(course)

    return detailed


def scrape_all(year, codes=None, fetch_details=True, delay=0.5):
    if codes is None:
        codes = ALL_CODES
    all_courses = []
    with httpx.Client(timeout=60, follow_redirects=True, verify=False) as client:
        for code in codes:
            try:
                courses = scrape_faculty(client, code, year, fetch_details, delay)
                all_courses.extend(courses)
            except Exception as e:
                print(f"  学部 {code} でエラー: {e}")
    return all_courses


def main():
    import argparse
    parser = argparse.ArgumentParser(description="信州大学シラバススクレイパー")
    parser.add_argument("years", type=int, nargs="+")
    parser.add_argument("--faculties", nargs="*", default=None)
    parser.add_argument("--undergrad-only", action="store_true")
    parser.add_argument("--no-details", action="store_true")
    parser.add_argument("--delay", type=float, default=0.5)
    args = parser.parse_args()

    codes = args.faculties
    if codes is None:
        codes = UNDERGRADUATE_CODES if args.undergrad_only else ALL_CODES

    Path("data").mkdir(exist_ok=True)
    for year in args.years:
        print(f"\n{'='*50}")
        print(f" {year}年度 シラバス取得開始")
        print(f"{'='*50}")
        courses = scrape_all(year, codes, not args.no_details, args.delay)
        path = Path("data") / f"courses_{year}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(courses, f, ensure_ascii=False, indent=2)
        print(f"\n{len(courses)} 件を {path} に保存しました")


if __name__ == "__main__":
    main()