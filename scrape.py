from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from typing import Iterable, List
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

SITE_ROOT = "https://www.contestkorea.com/sub/"
LIST_URL = urljoin(SITE_ROOT, "list.php")
DISPLAY_ROWS = 12
MAX_PAGES = 5
MAX_STORED_ITEMS = 50
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
    first_seen_at: str = ""
    last_seen_at: str = ""
    is_current: bool = True


session = requests.Session()
session.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
    }
)


def build_list_url(page: int) -> str:
    return f"{LIST_URL}?displayrow={DISPLAY_ROWS}&int_gbn=1&page={page}"


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


def detect_total_pages(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    pages: set[int] = set()

    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "")
        if "list.php" not in href:
            continue
        query = parse_qs(urlparse(urljoin(LIST_URL, href)).query)
        page_values = query.get("page") or query.get("Page")
        if not page_values:
            continue
        try:
            pages.add(int(page_values[0]))
        except ValueError:
            continue

    return max(pages) if pages else 1


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


def collect_current_contests() -> tuple[List[Contest], int, bool, int]:
    dedup: dict[str, Contest] = {}
    previous_signature: tuple[str, ...] | None = None
    pages_collected = 0
    duplicate_page_detected = False

    first_html = fetch_html(build_list_url(1))
    total_pages = detect_total_pages(first_html)
    page_htmls = [(1, first_html)]
    page_htmls.extend((page, fetch_html(build_list_url(page))) for page in range(2, min(total_pages, MAX_PAGES) + 1))

    for _, html in page_htmls:
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
    return contests, pages_collected, duplicate_page_detected, total_pages


def load_previous_contests() -> list[Contest]:
    if not OUTPUT_JSON.exists():
        return []
    try:
        payload = json.loads(OUTPUT_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    items = payload.get("items", [])
    contests: list[Contest] = []
    for item in items:
        try:
            contests.append(Contest(**item))
        except TypeError:
            continue
    return contests


def merge_contests(current_contests: list[Contest], previous_contests: list[Contest], generated_at: str) -> tuple[list[Contest], int]:
    merged: dict[str, Contest] = {contest.detail_url: contest for contest in previous_contests}
    new_count = 0

    for contest in current_contests:
        previous = merged.get(contest.detail_url)
        if previous:
            contest.first_seen_at = previous.first_seen_at or previous.last_seen_at or generated_at
        else:
            contest.first_seen_at = generated_at
            new_count += 1
        contest.last_seen_at = generated_at
        contest.is_current = True
        merged[contest.detail_url] = contest

    current_urls = {contest.detail_url for contest in current_contests}
    for url, contest in list(merged.items()):
        if url not in current_urls:
            contest.is_current = False
            if not contest.first_seen_at:
                contest.first_seen_at = contest.last_seen_at or generated_at
            merged[url] = contest

    ordered = sorted(
        merged.values(),
        key=lambda contest: (
            0 if contest.is_current else 1,
            -(datetime.strptime(contest.last_seen_at or generated_at, "%Y-%m-%d %H:%M:%S KST").timestamp()),
            contest.title,
        ),
    )
    return ordered[:MAX_STORED_ITEMS], new_count


def status_rank(contest: Contest) -> tuple[int, str, str]:
    status = contest.status_text
    if not contest.is_current:
        priority = 3
    elif "접수중" in status:
        priority = 0
    elif "접수예정" in status:
        priority = 1
    elif "마감" in status:
        priority = 2
    else:
        priority = 3
    return priority, contest.status_day, contest.title


def split_groups(contests: List[Contest]) -> tuple[List[Contest], List[Contest], List[Contest], List[Contest]]:
    current = [contest for contest in contests if contest.is_current]
    open_items = [contest for contest in current if "접수중" in contest.status_text]
    upcoming_items = [contest for contest in current if "접수예정" in contest.status_text]
    other_current = [contest for contest in current if contest not in open_items and contest not in upcoming_items]
    archived = [contest for contest in contests if not contest.is_current]
    return open_items, upcoming_items, other_current, archived


def render_card(contest: Contest) -> str:
    announcement = (
        f'<div><span>발표</span><strong>{escape(contest.announcement_date)}</strong></div>'
        if contest.announcement_date and contest.announcement_date != "-"
        else ""
    )
    seen_block = ""
    if contest.first_seen_at:
        seen_block += f'<div><span>처음 수집</span><strong>{escape(contest.first_seen_at)}</strong></div>'
    if contest.last_seen_at:
        seen_block += f'<div><span>마지막 확인</span><strong>{escape(contest.last_seen_at)}</strong></div>'
    archive_badge = '<span class="badge archive">보관됨</span>' if not contest.is_current else ""
    return f"""
      <article class=\"card\">
        <div class=\"card-top\">
          <div class=\"badge-wrap\">
            <span class=\"badge category\">{escape(contest.category)}</span>
            {archive_badge}
          </div>
          <span class=\"badge status\">{escape(contest.status_day)} {escape(contest.status_text)}</span>
        </div>
        <h3>{escape(contest.title)}</h3>
        <p>주최: {escape(contest.host)}</p>
        <p>대상: {escape(contest.target)}</p>
        <div class=\"meta\">
          <div><span>접수</span><strong>{escape(contest.reception_period)}</strong></div>
          <div><span>심사</span><strong>{escape(contest.evaluation_period)}</strong></div>
          {announcement}
          {seen_block}
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


def render_html(
    contests: List[Contest], generated_at: str, pages_collected: int, duplicate_page_detected: bool, total_pages: int, new_count: int
) -> str:
    contests = sorted(contests, key=status_rank)
    open_items, upcoming_items, other_current, archived = split_groups(contests)
    source_url = build_list_url(1)
    page_note = (
        f"실제 유효 수집 페이지: {pages_collected}페이지"
        if not duplicate_page_detected
        else f"실제 유효 수집 페이지: {pages_collected}페이지 (이후 페이지 응답이 중복되어 중단)"
    )

    sections = [
        render_section("접수중", "지금 바로 지원 가능한 공모전", open_items),
        render_section("접수예정", "곧 열리는 공모전", upcoming_items),
        render_section("기타 현재 항목", "현재 목록에 있지만 상태가 접수중/접수예정 외인 항목", other_current),
        render_section("보관된 이전 항목", "지금은 첫 페이지 최신 목록에서 내려갔지만 기록으로 보관한 공모전", archived),
    ]
    sections_html = "\n\n".join(section for section in sections if section)

    return f"""<!DOCTYPE html>
<html lang=\"ko\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>공모전 Daily Update</title>
  <meta name=\"description\" content=\"콘테스트코리아 공개 목록을 30분마다 다시 수집하고 이전 항목도 최대 50개까지 누적 보관하는 공모전 페이지\" />
  <style>
    :root {{
      --bg: #0f172a;
      --panel: rgba(17, 24, 39, 0.95);
      --text: #e5e7eb;
      --muted: #9ca3af;
      --border: rgba(255,255,255,0.08);
      --shadow: 0 14px 30px rgba(0,0,0,0.25);
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Pretendard, Arial, sans-serif; background: linear-gradient(180deg, #020617, #0f172a); color: var(--text); }}
    a {{ color: inherit; }}
    .wrap {{ max-width: 1200px; margin: 0 auto; padding: 40px 20px 80px; }}
    .hero {{ margin-bottom: 28px; }}
    .hero h1 {{ font-size: 2.4rem; margin: 0 0 12px; }}
    .hero p {{ margin: 0; color: var(--muted); line-height: 1.7; max-width: 900px; }}
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
    .badge-wrap {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .badge {{ display: inline-flex; align-items: center; padding: 6px 10px; border-radius: 999px; font-size: 0.8rem; }}
    .badge.category {{ background: rgba(245, 158, 11, 0.14); color: #fde68a; }}
    .badge.status {{ background: rgba(56, 189, 248, 0.14); color: #bae6fd; text-align: right; }}
    .badge.archive {{ background: rgba(244, 63, 94, 0.14); color: #fecdd3; }}
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
      <p>콘테스트코리아 공개 목록을 30분마다 다시 수집하고, 현재 목록에서 내려간 항목도 최대 {MAX_STORED_ITEMS}개까지 누적 보관합니다. 그래서 새 공모전이 올라오면 기존 12개를 덮어쓰는 대신 이전 항목도 기록으로 남습니다.</p>
    </section>

    <section class=\"summary\">
      <div class=\"pill\">누적 보관 {len(contests)}건</div>
      <div class=\"pill\">현재 항목 {len(open_items) + len(upcoming_items) + len(other_current)}건</div>
      <div class=\"pill\">보관된 이전 항목 {len(archived)}건</div>
      <div class=\"pill\">이번 실행 신규 추가 {new_count}건</div>
      <div class=\"pill\">마지막 업데이트: {escape(generated_at)}</div>
      <div class=\"pill\">갱신 주기: 30분</div>
      <div class=\"pill\">시도 범위: 최대 {MAX_PAGES}페이지 / 페이지당 {DISPLAY_ROWS}건</div>
      <div class=\"pill\">사이트 탐지 페이지 수: {total_pages}페이지</div>
      <div class=\"pill\">{escape(page_note)}</div>
    </section>

    {sections_html}

    <footer>
      데이터 출처: <a href=\"{escape(source_url, quote=True)}\" target=\"_blank\" rel=\"noopener noreferrer\">ContestKorea 공개 목록</a><br />
      수집 기준: `int_gbn=1` 목록을 조회하고, 상세 링크 기준으로 중복 제거 후 최대 {MAX_STORED_ITEMS}개까지 보관합니다. 현재 목록에 없는 항목은 삭제하지 않고 `보관됨` 상태로 남깁니다.
    </footer>
  </main>
</body>
</html>
"""


def main() -> None:
    current_contests, pages_collected, duplicate_page_detected, total_pages = collect_current_contests()
    generated_at = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")
    previous_contests = load_previous_contests()
    contests, new_count = merge_contests(current_contests, previous_contests, generated_at)

    contests = sorted(contests, key=status_rank)
    open_items, upcoming_items, other_current, archived = split_groups(contests)

    payload = {
        "source": LIST_URL,
        "filters": {
            "display_rows": DISPLAY_ROWS,
            "max_pages": MAX_PAGES,
            "max_stored_items": MAX_STORED_ITEMS,
            "int_gbn": 1,
            "status_priority": ["접수중", "접수예정", "기타 현재 항목", "보관된 이전 항목"],
        },
        "crawl_result": {
            "pages_collected": pages_collected,
            "duplicate_page_detected": duplicate_page_detected,
            "site_total_pages_detected": total_pages,
            "new_items_added_this_run": new_count,
        },
        "generated_at": generated_at,
        "count": len(contests),
        "counts_by_status": {
            "open": len(open_items),
            "upcoming": len(upcoming_items),
            "other_current": len(other_current),
            "archived": len(archived),
        },
        "items": [asdict(contest) for contest in contests],
    }

    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    OUTPUT_HTML.write_text(
        render_html(contests, generated_at, pages_collected, duplicate_page_detected, total_pages, new_count),
        encoding="utf-8",
    )

    print(f"Saved {len(contests)} contests to {OUTPUT_JSON} and {OUTPUT_HTML}")


if __name__ == "__main__":
    main()
