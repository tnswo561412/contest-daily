from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.contestkorea.com/sub/list.php?displayrow=12&int_gbn=1"
SITE_ROOT = "https://www.contestkorea.com/sub/"
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


def fetch_html(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
    }
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text


def clean_text(text: str) -> str:
    return " ".join(text.replace("\xa0", " ").split())


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

        date_map = {"reception": "", "evaluation": "", "announcement": ""}
        for span in item.select("div.date-detail > span"):
            label_node = span.find("em")
            label = clean_text(label_node.get_text()) if label_node else ""
            text = clean_text(span.get_text(" ", strip=True).replace(label, "", 1))
            if label == "접수":
                date_map["reception"] = text
            elif label == "심사":
                date_map["evaluation"] = text
            elif label == "발표":
                date_map["announcement"] = text

        host = clean_text(host_node.get_text(" ", strip=True).replace("주최", "").replace(".", "", 1)) if host_node else ""
        target = clean_text(target_node.get_text(" ", strip=True).replace("대상", "").replace(".", "", 1)) if target_node else ""

        contests.append(
            Contest(
                title=clean_text(title_node.get_text()),
                category=clean_text(category_node.get_text()) if category_node else "",
                host=host,
                target=target,
                reception_period=date_map["reception"],
                evaluation_period=date_map["evaluation"],
                announcement_date=date_map["announcement"],
                status_day=clean_text(day_node.get_text()) if day_node else "",
                status_text=clean_text(condition_node.get_text()) if condition_node else "",
                detail_url=urljoin(SITE_ROOT, title_anchor.get("href", "")),
            )
        )

    if not contests:
        raise RuntimeError("파싱된 공모전이 없습니다. 사이트 구조가 바뀌었는지 확인하세요.")

    return contests


def render_html(contests: List[Contest], generated_at: str) -> str:
    cards = []
    for contest in contests:
        announcement = f"<div><span>발표</span><strong>{contest.announcement_date}</strong></div>" if contest.announcement_date else ""
        cards.append(
            f"""
            <article class=\"card\">
              <div class=\"card-top\">
                <span class=\"badge category\">{contest.category}</span>
                <span class=\"badge status\">{contest.status_day} {contest.status_text}</span>
              </div>
              <h2>{contest.title}</h2>
              <p class=\"host\">주최: {contest.host}</p>
              <p class=\"target\">대상: {contest.target}</p>
              <div class=\"meta\">
                <div><span>접수</span><strong>{contest.reception_period}</strong></div>
                <div><span>심사</span><strong>{contest.evaluation_period or '-'} </strong></div>
                {announcement}
              </div>
              <a href=\"{contest.detail_url}\" target=\"_blank\" rel=\"noopener noreferrer\">상세 보기</a>
            </article>
            """.strip()
        )

    cards_html = "\n".join(cards)
    return f"""<!DOCTYPE html>
<html lang=\"ko\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>공모전 Daily Update</title>
  <meta name=\"description\" content=\"30분마다 자동으로 갱신되는 공모전 공개 페이지\" />
  <style>
    :root {{
      --bg: #0f172a;
      --panel: #111827;
      --panel-2: #1f2937;
      --text: #e5e7eb;
      --muted: #9ca3af;
      --accent: #38bdf8;
      --accent-2: #f59e0b;
      --border: rgba(255,255,255,0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Pretendard, Arial, sans-serif; background: linear-gradient(180deg, #020617, #0f172a); color: var(--text); }}
    .wrap {{ max-width: 1100px; margin: 0 auto; padding: 40px 20px 80px; }}
    .hero {{ margin-bottom: 28px; }}
    .hero h1 {{ font-size: 2.4rem; margin: 0 0 12px; }}
    .hero p {{ margin: 0; color: var(--muted); line-height: 1.6; }}
    .summary {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 24px 0 32px; }}
    .summary .pill {{ background: rgba(56, 189, 248, 0.12); color: #bae6fd; border: 1px solid rgba(56, 189, 248, 0.25); padding: 10px 14px; border-radius: 999px; font-size: 0.95rem; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 18px; }}
    .card {{ background: rgba(17, 24, 39, 0.95); border: 1px solid var(--border); border-radius: 18px; padding: 18px; box-shadow: 0 14px 30px rgba(0,0,0,0.25); }}
    .card-top {{ display: flex; justify-content: space-between; gap: 8px; margin-bottom: 12px; }}
    .badge {{ display: inline-flex; align-items: center; padding: 6px 10px; border-radius: 999px; font-size: 0.8rem; }}
    .badge.category {{ background: rgba(245, 158, 11, 0.14); color: #fde68a; }}
    .badge.status {{ background: rgba(56, 189, 248, 0.14); color: #bae6fd; text-align: right; }}
    .card h2 {{ margin: 0 0 12px; font-size: 1.18rem; line-height: 1.45; }}
    .card p {{ margin: 6px 0; color: var(--muted); line-height: 1.5; }}
    .meta {{ display: grid; gap: 10px; margin: 16px 0; padding: 14px; background: rgba(255,255,255,0.03); border-radius: 14px; }}
    .meta div {{ display: flex; justify-content: space-between; gap: 12px; }}
    .meta span {{ color: var(--muted); }}
    .meta strong {{ color: var(--text); text-align: right; }}
    .card a {{ display: inline-block; margin-top: 8px; color: white; text-decoration: none; background: linear-gradient(90deg, #0ea5e9, #2563eb); padding: 10px 14px; border-radius: 12px; font-weight: 600; }}
    footer {{ margin-top: 40px; color: var(--muted); font-size: 0.95rem; }}
  </style>
</head>
<body>
  <main class=\"wrap\">
    <section class=\"hero\">
      <h1>공모전 Daily Update</h1>
      <p>콘테스트코리아 공개 목록을 기준으로 주요 공모전 정보를 수집해 30분마다 자동 갱신하는 페이지입니다.</p>
    </section>

    <section class=\"summary\">
      <div class=\"pill\">총 {len(contests)}건 수집</div>
      <div class=\"pill\">마지막 업데이트: {generated_at}</div>
      <div class=\"pill\">갱신 주기: 30분</div>
      <div class=\"pill\">배포 방식: GitHub Pages</div>
    </section>

    <section class=\"grid\">
      {cards_html}
    </section>

    <footer>
      데이터 출처: ContestKorea 공개 목록 페이지 / GitHub Actions가 30분마다 스크래핑 후 변경 사항이 있을 때만 자동 커밋합니다.
    </footer>
  </main>
</body>
</html>
"""


def main() -> None:
    html = fetch_html(BASE_URL)
    contests = parse_contests(html)
    generated_at = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")

    payload = {
        "source": BASE_URL,
        "generated_at": generated_at,
        "count": len(contests),
        "items": [asdict(contest) for contest in contests],
    }

    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    OUTPUT_HTML.write_text(render_html(contests, generated_at), encoding="utf-8")

    print(f"Saved {len(contests)} contests to {OUTPUT_JSON} and {OUTPUT_HTML}")


if __name__ == "__main__":
    main()
