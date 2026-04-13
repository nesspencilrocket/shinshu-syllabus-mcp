# shinshu-syllabus-mcp

MCP server for searching Shinshu University course syllabi.

Search Shinshu University courses in natural language from Claude Code or any MCP-compatible AI tool.

## Data Source

Public syllabus data from [campus-3.shinshu-u.ac.jp/syllabusj/](https://campus-3.shinshu-u.ac.jp/syllabusj/Top). No authentication required.

## Tools

| Tool | Description |
| --- | --- |
| `search_courses` | Search by keyword, instructor, faculty, period, day, credits, target students |
| `get_course` | Get full course details by ID |
| `get_course_by_code` | Search by registration code |
| `list_instructors` | List all instructors (with optional filter by name or faculty) |
| `list_faculties` | List all faculties/departments with course counts |
| `course_stats` | Get statistics (total courses, by period/faculty/day/credits) |

## Supported Faculties

### Undergraduate (学部)

| Code | Faculty |
| --- | --- |
| `L` | 人文学部 (Faculty of Arts) |
| `E` | 教育学部 (Faculty of Education) |
| `J` | 経法学部 (Faculty of Economics and Law) |
| `S` | 理学部 (Faculty of Science) |
| `M` | 医学部 (Faculty of Medicine) |
| `T` | 工学部 (Faculty of Engineering) |
| `A` | 農学部 (Faculty of Agriculture) |
| `F` | 繊維学部 (Faculty of Textile Science and Technology) |
| `G` | 共通教育 (General Education) |
| `R2` | グローバル化推進センター (Center for Global Education) |

### Graduate Schools (大学院)

| Code | Graduate School |
| --- | --- |
| `EA` | 教育学研究科 |
| `UA` | 総合人文社会科学研究科 |
| `MS` | 医学系研究科（修士課程） |
| `SS` | 総合理工学研究科（理学専攻） |
| `TS` | 総合理工学研究科（工学専攻） |
| `FS` | 総合理工学研究科（繊維学専攻） |
| `AS` | 総合理工学研究科（農学専攻） |
| `BS` | 総合理工学研究科（生命医工学専攻） |
| `HM` | 総合医理工学研究科（医学系専攻） |
| `HS` | 総合医理工学研究科（総合理工学専攻） |
| `HB` | 総合医理工学研究科（生命医工学専攻） |
| `ST` | 総合工学系研究科 |

## Setup

### 1. Clone

```bash
git clone https://github.com/YOUR_USERNAME/shinshu-syllabus-mcp.git
cd shinshu-syllabus-mcp
```

### 2. Install dependencies

```bash
uv sync
```

Or with pip:

```bash
pip install -r requirements.txt
```

### 3. Scrape syllabus data

```bash
# 全学部（学部のみ、大学院を除く）
uv run python scraper.py 2025 --undergrad-only

# 全学部 + 大学院
uv run python scraper.py 2025

# 特定の学部のみ（例: 工学部と理学部）
uv run python scraper.py 2025 --faculties T S

# 一覧のみ取得（高速、詳細ページは取得しない）
uv run python scraper.py 2025 --no-details

# 複数年度
uv run python scraper.py 2024 2025
```

Outputs `data/courses_2025.json`.

> **Note:** スクレイピングには学部数に応じて数分〜数十分かかります。  
> サーバーへの負荷を考慮し、`--delay` オプション（デフォルト: 0.3秒）でリクエスト間隔を調整できます。

### 4. Register with Claude Code

```bash
claude mcp add shinshu-syllabus -- uv run --directory /path/to/shinshu-syllabus-mcp python server.py
```

Replace `/path/to/` with the actual path.

### 5. Verify

Run `/mcp` in Claude Code to confirm the server is connected.

## Usage Examples

Ask Claude Code things like:

- 「信州大学でプログラミング系の授業を教えて」
- 「工学部の月曜の授業一覧」
- 「前期に開講される英語の授業は？」
- 「山田先生の担当科目を調べて」
- 「理学部の1年生向けの科目を検索」
- 「共通教育で単位2の授業を探して」
- "Search for data science courses at Shinshu University"
- "List courses taught on Wednesdays in the Faculty of Engineering"

## Update Data

Re-run the scraper each semester:

```bash
uv run python scraper.py 2025 2026
```

Multiple years can be specified at once.

## Project Structure

```
shinshu-syllabus-mcp/
├── scraper.py          # Syllabus scraper
├── server.py           # MCP server
├── pyproject.toml      # Project config
├── .python-version
├── .gitignore
├── LICENSE
├── README.md
└── data/               # Scraped data (gitignored)
    └── courses_2025.json
```

## Tech Stack

- Python 3.12
- [FastMCP](https://github.com/modelcontextprotocol/python-sdk) (MCP Python SDK)
- httpx + BeautifulSoup4 (scraping)

## Notes

- シラバスデータは [信州大学シラバス検索システム](https://campus-3.shinshu-u.ac.jp/syllabusj/Top) の公開データを利用しています。
- スクレイピング実行時はサーバーへの負荷に配慮し、適切な間隔を設定してください。

## License

MIT

---

# shinshu-syllabus-mcp（日本語）

信州大学のシラバスを検索できるMCPサーバー。

Claude Code や他のMCP対応AIツールから、信州大学の授業を自然言語で検索できます。

## データソース

[campus-3.shinshu-u.ac.jp/syllabusj/](https://campus-3.shinshu-u.ac.jp/syllabusj/Top) の公開シラバスデータ。認証不要。

## 提供ツール

| ツール | 説明 |
| --- | --- |
| `search_courses` | 科目名・教員名・学部・曜日・学期・単位数・対象学生で検索 |
| `get_course` | 科目IDで詳細取得（授業のねらい・概要・計画・成績評価・教科書等） |
| `get_course_by_code` | 登録コード（科目コード）で検索 |
| `list_instructors` | 教員一覧（学部・名前で絞り込み可） |
| `list_faculties` | 学部・研究科一覧と科目数 |
| `course_stats` | 統計情報（科目数・学期別・学部別・曜日別・単位別） |

## セットアップ

### 1. クローン

```bash
git clone https://github.com/YOUR_USERNAME/shinshu-syllabus-mcp.git
cd shinshu-syllabus-mcp
```

### 2. 依存関係インストール

```bash
uv sync
```

### 3. シラバスデータ取得

```bash
# 学部のみ（推奨・初回）
uv run python scraper.py 2025 --undergrad-only

# 全学部 + 大学院
uv run python scraper.py 2025

# 特定の学部のみ
uv run python scraper.py 2025 --faculties T S A
```

年度を指定して実行。`data/courses_2025.json` が生成されます。

### 4. Claude Code に登録

```bash
claude mcp add shinshu-syllabus -- uv run --directory /path/to/shinshu-syllabus-mcp python server.py
```

`/path/to/` を実際のパスに置き換えてください。

### 5. 動作確認

Claude Code で `/mcp` を実行してサーバーが接続されていることを確認。

## 使い方の例

Claude Code に以下のように聞けます：

- 「信州大学でプログラミング系の授業を教えて」
- 「工学部の月曜の前期の授業一覧」
- 「英語で開講されている授業は？」
- 「データサイエンス系の授業を探して」
- 「山田先生の担当科目は？」
- 「理学部の統計情報を見せて」
- 「共通教育の1年生向け科目を探して」

## データ更新

学期ごとにスクレイパーを再実行：

```bash
uv run python scraper.py 2025 2026
```

複数年度を同時に指定可能。

## 注意事項


- シラバスデータは公開情報ですが、スクレイピング時はサーバー負荷に配慮してください。
