from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from typing import Iterable, List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

SITE_ROOT = "https://www.contestkorea.com/sub/"
LIST_URL = urljoin(SITE_ROOT, "list.php")
DISPLAY_ROWS = 12
MAX_PAGES = 5
REQUEST_TIMEOUT = 30
KST = timezone(timedelta(hours=9))
OUTPUT_JSON = Path("contests.json")
OUTPUT_HTML = Path("index.html")


@dataclass
class Contest:
    title: str
    category: str
    host: str
    target: str
    reception_period: str
    evaluation_period: str
    announcement_date: str
    status_day: str
    status_text: str
    detail_url: str


session = requests.Session()
session.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
    }
)


def build_list_url(page: int) -> str:
    return f"{LIST_URL}?displayrow={DISPLAY_ROWS}&int_gbn=1&Page={page}"


def fetch_html(url: str) -> str:
    response = session.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.text


def clean_text(text: str) -> str:
    return " ".join(text.replace("\xa0", " ").split())


def normalize_field(text: str, prefixes: Iterable[str] = ()) -> str:
    value = clean_text(text)
    for prefix in prefixes:
        if value.startswith(prefix):
            value = value[len(prefix) :].strip()
    return value.strip(" .:-")


def parse_contests(html: str) -> List[Contest]:
    soup = BeautifulSoup(html, "html.parser")
    container = soup.select_one("div.list_style_2 > ul")
    if not container:
        raise RuntimeError("공모전 목록 영역을 찾지 못했습니다.")

    contests: List[Contest] = []

    for item in container.find_all("li", recursive=False):
        title_anchor = item.select_one("div.title > a")
        title_node = item.select_one("div.title .txt")
        category_node = item.select_one("div.title .category")
        host_node = item.select_one("ul.host li.icon_1")
        target_node = item.select_one("ul.host li.icon_2")
        day_node = item.select_one("div.d-day .day")
        condition_node = item.select_one("div.d-day .condition")

        if not title_anchor or not title_node:
            continue

        date_map = {"reception": "-", "evaluation": "-", "announcement": "-"}
        for span in item.select("div.date-detail > span"):
            label_node = span.find("em")
            label = clean_text(label_node.get_text()) if label_node else ""
            text = clean_text(span.get_text(" ", strip=True).replace(label, "", 1)) or "-"
            if label == "접수":
                date_map["reception"] = text
            elif label == "심사":
                date_map["evaluation"] = text
            elif label == "발표":
                date_map["announcement"] = text

        host = normalize_field(host_node.get_text(" ", strip=True), prefixes=("주최",)) if host_node else "-"
        target = normalize_field(target_node.get_text(" ", strip=True), prefixes=("대상",)) if target_node else "-"

        contests.append(
            Contest(
                title=clean_text(title_node.get_text()) or "제목 없음",
                category=clean_text(category_node.get_text()) if category_node else "기타",
                host=host or "-",
                target=target or "-",
                reception_period=date_map["reception"],
                evaluation_period=date_map["evaluation"],
                announcement_date=date_map["announcement"],
                status_day=clean_text(day_node.get_text()) if day_node else "-",
                status_text=clean_text(condition_node.get_text()) if condition_node else "상태 미상",
                detail_url=urljoin(SITE_ROOT, title_anchor.get("href", "")),
            )
        )

    return contests


def collect_contests() -> tuple[List[Contest], int, bool]:
    dedup: dict[str, Contest] = {}
    previous_signature: tuple[str, ...] | None = None
    pages_collected = 0
    duplicate_page_detected = False

    for page in range(1, MAX_PAGES + 1):
        html = fetch_html(build_list_url(page))
        page_items = parse_contests(html)
        if not page_items:
            break

        signature = tuple(contest.detail_url for contest in page_items)
        if previous_signature == signature:
            duplicate_page_detected = True
            break

        pages_collected += 1
        previous_signature = signature

        for contest in page_items:
            dedup.setdefault(contest.detail_url, contest)

    contests = list(dedup.values())
    if not contests:
        raise RuntimeError("파싱된 공모전이 없습니다. 사이트 구조가 바뀌었는지 확인하세요.")
    return contests, pages_collected, duplicate_page_detected


def status_rank(contest: Contest) -> tuple[int, str, str]:
    status = contest.status_text
    if "접수중" in status:
        priority = 0
    elif "접수예정" in status:
        priority = 1
    elif "마감" in status:
        priority = 2
    else:
        priority = 3
    return priority, contest.status_day, contest.title


def split_groups(contests: List[Contest]) -> tuple[List[Contest], List[Contest], List[Contest]]:
    open_items = [contest for contest in contests if "접수중" in contest.status_text]
    upcoming_items = [contest for contest in contests if "접수예정" in contest.status_text]
    others = [contest for contest in contests if contest not in open_items and contest not in upcoming_items]
    return open_items, upcoming_items, others


def render_card(contest: Contest) -> str:
    announcement = (
        f'<div><span>발표</span><strong>{escape(contest.announcement_date)}</strong></div>'
        if contest.announcement_date and contest.announcement_date != "-"
        else ""
    )
    return f"""
      <article class=\"card\">
        <div class=\"card-top\">
          <span class=\"badge category\">{escape(contest.category)}</span>
          <span class=\"badge status\">{escape(contest.status_day)} {escape(contest.status_text)}</span>
        </div>
        <h3>{escape(contest.title)}</h3>
        <p>주최: {escape(contest.host)}</p>
        <p>대상: {escape(contest.target)}</p>
        <div class=\"meta\">
          <div><span>접수</span><strong>{escape(contest.reception_period)}</strong></div>
          <div><span>심사</span><strong>{escape(contest.evaluation_period)}</strong></div>
          {announcement}
        </div>
        <a href=\"{escape(contest.detail_url, quote=True)}\" target=\"_blank\" rel=\"noopener noreferrer\">상세 보기</a>
      </article>
    """.strip()


def render_section(title: str, subtitle: str, contests: List[Contest]) -> str:
    if not contests:
        return ""
    cards_html = "\n".join(render_card(contest) for contest in contests)
    return f"""
    <section class=\"section\">
      <div class=\"section-head\">
        <div>
          <h2>{escape(title)}</h2>
          <p>{escape(subtitle)}</p>
        </div>
        <span class=\"count\">{len(contests)}건</span>
      </div>
      <div class=\"grid\">
        {cards_html}
      </div>
    </section>
    """.strip()


def render_html(contests: List[Contest], generated_at: str, pages_collected: int, duplicate_page_detected: bool) -> str:
    contests = sorted(contests, key=status_rank)
    open_items, upcoming_items, others = split_groups(contests)
    source_url = build_list_url(1)
    page_note = (
        f"실제 유효 수집 페이지: {pages_collected}페이지"
        if not duplicate_page_detected
        else f"실제 유효 수집 페이지: {pages_collected}페이지 (이후 페이지 응답이 중복되어 중단)"
    )

    sections = [
        render_section("접수중", "지금 바로 지원 가능한 공모전", open_items),
        render_section("접수예정", "곧 열리는 공모전", upcoming_items),
        render_section("기타", "상태가 접수중/접수예정 외로 표시된 항목", others),
    ]
    sections_html = "\n\n".join(section for section in sections if section)

    return f"""<!DOCTYPE html>
<html lang=\"ko\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>공모전 Daily Update</title>
  <meta name=\"description\" content=\"콘테스트코리아 공개 목록을 30분마다 다시 수집해 보여주는 공모전 페이지\" />
  <style>
    :root {{
      --bg: #0f172a;
      --panel: rgba(17, 24, 39, 0.95);
      --panel-2: #1f2937;
      --text: #e5e7eb;
      --muted: #9ca3af;
      --accent: #38bdf8;
      --accent-2: #f59e0b;
      --border: rgba(255,255,255,0.08);
      --shadow: 0 14px 30px rgba(0,0,0,0.25);
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Pretendard, Arial, sans-serif; background: linear-gradient(180deg, #020617, #0f172a); color: var(--text); }}
    a {{ color: inherit; }}
    .wrap {{ max-width: 1200px; margin: 0 auto; padding: 40px 20px 80px; }}
    .hero {{ margin-bottom: 28px; }}
    .hero h1 {{ font-size: 2.4rem; margin: 0 0 12px; }}
    .hero p {{ margin: 0; color: var(--muted); line-height: 1.7; max-width: 860px; }}
    .summary {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 24px 0 36px; }}
    .pill {{ background: rgba(56, 189, 248, 0.12); color: #bae6fd; border: 1px solid rgba(56, 189, 248, 0.25); padding: 10px 14px; border-radius: 999px; font-size: 0.95rem; }}
    .section {{ margin-top: 34px; }}
    .section-head {{ display: flex; justify-content: space-between; gap: 16px; align-items: end; margin-bottom: 16px; }}
    .section-head h2 {{ margin: 0 0 6px; font-size: 1.45rem; }}
    .section-head p {{ margin: 0; color: var(--muted); }}
    .count {{ color: #bae6fd; background: rgba(56, 189, 248, 0.12); border: 1px solid rgba(56, 189, 248, 0.25); padding: 8px 12px; border-radius: 999px; white-space: nowrap; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 18px; }}
    .card {{ background: var(--panel); border: 1px solid var(--border); border-radius: 18px; padding: 18px; box-shadow: var(--shadow); }}
    .card-top {{ display: flex; justify-content: space-between; gap: 8px; margin-bottom: 12px; }}
    .badge {{ display: inline-flex; align-items: center; padding: 6px 10px; border-radius: 999px; font-size: 0.8rem; }}
    .badge.category {{ background: rgba(245, 158, 11, 0.14); color: #fde68a; }}
    .badge.status {{ background: rgba(56, 189, 248, 0.14); color: #bae6fd; text-align: right; }}
    .card h3 {{ margin: 0 0 12px; font-size: 1.08rem; line-height: 1.45; }}
    .card p {{ margin: 6px 0; color: var(--muted); line-height: 1.5; }}
    .meta {{ display: grid; gap: 10px; margin: 16px 0; padding: 14px; background: rgba(255,255,255,0.03); border-radius: 14px; }}
    .meta div {{ display: flex; justify-content: space-between; gap: 12px; }}
    .meta span {{ color: var(--muted); }}
    .meta strong {{ color: var(--text); text-align: right; }}
    .card a {{ display: inline-block; margin-top: 8px; color: white; text-decoration: none; background: linear-gradient(90deg, #0ea5e9, #2563eb); padding: 10px 14px; border-radius: 12px; font-weight: 600; }}
    footer {{ margin-top: 44px; color: var(--muted); font-size: 0.95rem; line-height: 1.7; }}
    @media (max-width: 720px) {{
      .section-head {{ flex-direction: column; align-items: start; }}
      .card-top {{ flex-direction: column; align-items: start; }}
    }}
  </style>
</head>
<body>
  <main class=\"wrap\">
    <section class=\"hero\">
      <h1>공모전 Daily Update</h1>
      <p>콘테스트코리아 공개 목록을 기준으로 최근 공모전 데이터를 다시 수집해 보여줍니다. GitHub Actions가 30분마다 실행되고, 변경이 있을 때만 결과 파일을 업데이트합니다.</p>
    </section>

    <section class=\"summary\">
      <div class=\"pill\">총 {len(contests)}건 수집</div>
      <div class=\"pill\">접수중 {len(open_items)}건</div>
      <div class=\"pill\">접수예정 {len(upcoming_items)}건</div>
      <div class=\"pill\">마지막 업데이트: {escape(generated_at)}</div>
      <div class=\"pill\">갱신 주기: 30분</div>
      <div class=\"pill\">시도 범위: 최대 {MAX_PAGES}페이지 / 페이지당 {DISPLAY_ROWS}건</div>
      <div class=\"pill\">{escape(page_note)}</div>
    </section>

    {sections_html}

    <footer>
      데이터 출처: <a href=\"{escape(source_url, quote=True)}\" target=\"_blank\" rel=\"noopener noreferrer\">ContestKorea 공개 목록</a><br />
      수집 기준: `int_gbn=1` 목록을 조회하고, 상태를 `접수중 → 접수예정 → 기타` 순으로 정리합니다. 상세 링크 기준으로 중복 제거하며, 페이지 응답이 반복되면 추가 수집을 중단합니다.
    </footer>
  </main>
</body>
</html>
"""


def main() -> None:
    contests, pages_collected, duplicate_page_detected = collect_contests()
    generated_at = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")

    contests = sorted(contests, key=status_rank)
    open_items, upcoming_items, others = split_groups(contests)

    payload = {
        "source": LIST_URL,
        "filters": {
            "display_rows": DISPLAY_ROWS,
            "max_pages": MAX_PAGES,
            "int_gbn": 1,
            "status_priority": ["접수중", "접수예정", "기타"],
        },
        "crawl_result": {
            "pages_collected": pages_collected,
            "duplicate_page_detected": duplicate_page_detected,
        },
        "generated_at": generated_at,
        "count": len(contests),
        "counts_by_status": {
            "open": len(open_items),
            "upcoming": len(upcoming_items),
            "other": len(others),
        },
        "items": [asdict(contest) for contest in contests],
    }

    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    OUTPUT_HTML.write_text(render_html(contests, generated_at, pages_collected, duplicate_page_detected), encoding="utf-8")

    print(f"Saved {len(contests)} contests to {OUTPUT_JSON} and {OUTPUT_HTML}")


if __name__ == "__main__":
    main()
