#!/usr/bin/env python3
"""네이버 블로그 전체 글 목록 → 구글 제출용 사이트맵(sitemap.xml) + 링크 목록(urls.txt)

사용법:
  python naver_blog_sitemap.py 블로그ID
  python naver_blog_sitemap.py https://blog.naver.com/블로그ID
  python naver_blog_sitemap.py 블로그ID --out 폴더 --pc

옵션:
  --out DIR      결과 저장 폴더 (기본: 현재 폴더)
  --pc           blog.naver.com 주소로 출력 (기본은 m.blog.naver.com)
  --delay SEC    페이지 요청 사이 대기 시간 (기본 0.5초)

결과:
  sitemap_<ID>.xml   구글 사이트맵 형식 (블로그 홈 + 전체 글, 5만 개 넘으면 여러 파일 + 인덱스)
  urls_<ID>.txt      한 줄에 하나씩 주소 (첫 줄은 블로그 홈)
  links_<ID>.txt     제목 / 링크 / 빈 줄 형식의 글 목록 (최신 글이 위)
  posts_<ID>.csv     주소, 제목, 작성일

표준 라이브러리만 사용합니다 (추가 설치 필요 없음). Python 3.8+
전체 공개 글만 나옵니다.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

LIST_URL = "https://blog.naver.com/PostTitleListAsync.naver"
PER_PAGE = 30  # 네이버가 허용하는 최대값
SITEMAP_MAX = 50000
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"


def parse_blog_id(arg: str) -> str:
    arg = arg.strip()
    m = re.search(r"blogId=([A-Za-z0-9_-]+)", arg)
    if m:
        return m.group(1)
    m = re.search(r"blog\.naver\.com/([A-Za-z0-9_-]+)", arg)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]+", arg):
        return arg
    sys.exit(f"블로그 ID를 알 수 없어요: {arg}")


def fetch_page(blog_id: str, page: int, retries: int = 3) -> dict:
    q = urllib.parse.urlencode({
        "blogId": blog_id, "viewdate": "", "currentPage": page,
        "categoryNo": 0, "parentCategoryNo": "", "countPerPage": PER_PAGE,
    })
    req = urllib.request.Request(f"{LIST_URL}?{q}", headers={
        "User-Agent": UA, "Referer": f"https://blog.naver.com/{blog_id}",
    })
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                text = r.read().decode("utf-8", errors="replace")
            # 응답에 JSON에서 허용되지 않는 \' 이스케이프가 섞여 있을 수 있음
            text = text.replace("\\'", "'")
            return json.loads(text, strict=False)
        except Exception as e:  # 네트워크 오류, 잘못된 JSON
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"{page}페이지 요청 실패: {last}")


def parse_date(s: str) -> str | None:
    """'2026. 11. 4.' → '2026-11-04'. '3시간 전' 같은 최근 글은 오늘 날짜."""
    s = (s or "").strip()
    m = re.match(r"(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})", s)
    if m:
        return dt.date(*map(int, m.groups())).isoformat()
    if re.search(r"(분|시간|초)\s*전|방금", s):
        return dt.date.today().isoformat()
    if "어제" in s:
        return (dt.date.today() - dt.timedelta(days=1)).isoformat()
    return None


def collect(blog_id: str, delay: float) -> list[dict]:
    first = fetch_page(blog_id, 1)
    if first.get("resultCode") != "S":
        sys.exit(f"목록을 가져오지 못했어요 (ID 확인, 비공개 블로그 여부 확인): {first.get('resultMessage')}")
    total = int(first.get("totalCount") or 0)
    pages = max(1, -(-total // PER_PAGE))
    print(f"블로그 '{blog_id}': 공개 글 {total}개, {pages}페이지")

    posts, seen = [], set()
    data = first
    for page in range(1, pages + 1):
        if page > 1:
            time.sleep(delay)
            data = fetch_page(blog_id, page)
            if data.get("resultCode") != "S":
                print(f"  {page}페이지에서 중단: {data.get('resultMessage')}")
                break
        items = data.get("postList") or []
        if not items:
            break
        for it in items:
            log_no = str(it.get("logNo", "")).strip()
            if not log_no or log_no in seen:
                continue
            seen.add(log_no)
            posts.append({
                "logNo": log_no,
                "title": urllib.parse.unquote_plus(it.get("title", "")).replace("&#39;", "'").replace("&quot;", '"').replace("&amp;", "&"),
                "date": parse_date(it.get("addDate", "")),
                "rawDate": it.get("addDate", ""),
            })
        print(f"  {page}/{pages}페이지 완료 (누적 {len(posts)}개)", end="\r")
    print()
    return posts


def write_sitemaps(urls_dates: list[tuple[str, str | None]], out: Path, blog_id: str) -> list[Path]:
    chunks = [urls_dates[i:i + SITEMAP_MAX] for i in range(0, len(urls_dates), SITEMAP_MAX)] or [[]]
    files = []
    for i, chunk in enumerate(chunks, 1):
        name = f"sitemap_{blog_id}.xml" if len(chunks) == 1 else f"sitemap_{blog_id}_{i}.xml"
        lines = ['<?xml version="1.0" encoding="UTF-8"?>',
                 '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
        for url, date in chunk:
            lines.append("  <url>")
            lines.append(f"    <loc>{escape(url)}</loc>")
            if date:
                lines.append(f"    <lastmod>{date}</lastmod>")
            lines.append("  </url>")
        lines.append("</urlset>")
        p = out / name
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        files.append(p)
    if len(files) > 1:  # 5만 개 초과 시 인덱스 파일
        idx = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
        idx += [f"  <sitemap><loc>{escape(f.name)}</loc></sitemap>" for f in files]
        idx.append("</sitemapindex>")
        p = out / f"sitemap_{blog_id}_index.xml"
        p.write_text("\n".join(idx) + "\n", encoding="utf-8")
        files.append(p)
    return files


def collect_blogger(blog_url: str) -> list[dict]:
    """Blogger(blogspot) 공개 글 목록을 피드(JSON)로 가져온다. 최신 글이 위."""
    base = blog_url.rstrip("/")
    if not base.startswith("http"):
        base = "https://" + base
    base = re.sub(r"/sitemap\.xml$", "", base)
    posts, start, size = [], 1, 150
    while True:
        q = urllib.parse.urlencode({"alt": "json", "max-results": size, "start-index": start})
        req = urllib.request.Request(f"{base}/feeds/posts/default?{q}", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            feed = json.load(r)["feed"]
        entries = feed.get("entry", [])
        for e in entries:
            url = next((l["href"] for l in e.get("link", []) if l.get("rel") == "alternate"), None)
            if not url:
                continue
            posts.append({
                "url": url,
                "title": e.get("title", {}).get("$t", "").strip() or url,
                "date": e.get("published", {}).get("$t", "")[:10] or None,
            })
        if len(entries) < size:
            break
        start += size
    print(f"Blogger '{base}': 공개 글 {len(posts)}개")
    return posts


def write_hub(sections: list[dict], hub: Path, site_url: str) -> None:
    """구글봇용 링크 모음 사이트. 사이트맵에는 이 사이트 주소만 넣는다
    (사이트맵에 다른 도메인 주소를 넣으면 구글이 무시함). 블로그 글은
    index.html 안의 <a href> 링크로 구글봇이 따라간다.
    sections: [{"name", "home", "posts": [{url, title, date}]}]"""
    hub.mkdir(parents=True, exist_ok=True)
    site_url = site_url.rstrip("/") + "/"
    h = lambda s: escape(s, {'"': "&quot;"})
    total = sum(len(s["posts"]) for s in sections)
    dates = [p["date"] for s in sections for p in s["posts"] if p["date"]]
    updated = max(dates) if dates else dt.date.today().isoformat()

    blocks = []
    for s in sections:
        items = "\n".join(
            f'      <li><a href="{h(p["url"])}">{h(p["title"])}</a>'
            + (f' <time datetime="{p["date"]}">{p["date"]}</time>' if p["date"] else "")
            + "</li>"
            for p in s["posts"]
        )
        blocks.append(f"""    <section>
    <h2>{h(s["name"])}</h2>
    <p class="meta"><a href="{h(s["home"])}">{h(s["home"])}</a> · 글 {len(s["posts"])}개</p>
    <ul>
{items}
    </ul>
    </section>""")
    names = " · ".join(s["name"] for s in sections)
    html = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>블로그 글 모음</title>
  <meta name="description" content="{h(names)} 전체 글 목록 ({total}개)">
  <link rel="canonical" href="{h(site_url)}">
  <style>
    body {{ font-family: system-ui, -apple-system, "Malgun Gothic", sans-serif; max-width: 760px; margin: 0 auto; padding: 24px 16px; line-height: 1.6; color: #222; background: #fff; }}
    h1 {{ font-size: 1.4rem; margin-bottom: .2rem; }}
    h2 {{ font-size: 1.15rem; margin: 2rem 0 .2rem; }}
    p.meta {{ color: #666; margin-top: 0; }}
    ul {{ list-style: none; padding: 0; }}
    li {{ padding: 10px 0; border-bottom: 1px solid #eee; }}
    a {{ color: #0a58ca; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    time {{ display: block; color: #888; font-size: .85rem; }}
  </style>
</head>
<body>
  <main>
    <h1>블로그 글 모음</h1>
    <p class="meta">글 {total}개 · 업데이트 {updated}</p>
{chr(10).join(blocks)}
  </main>
</body>
</html>
"""
    (hub / "index.html").write_text(html, encoding="utf-8")
    (hub / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"  <url>\n    <loc>{escape(site_url)}</loc>\n    <lastmod>{updated}</lastmod>\n  </url>\n"
        "</urlset>\n", encoding="utf-8")
    (hub / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\n\nSitemap: {site_url}sitemap.xml\n", encoding="utf-8")
    (hub / ".nojekyll").write_text("", encoding="utf-8")
    print(f"링크 모음 사이트 생성: {hub / 'index.html'} (글 {total}개)")


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="네이버 블로그 글 목록 → 사이트맵/링크 목록")
    ap.add_argument("blog", help="블로그 ID 또는 주소 (예: myblog, https://blog.naver.com/myblog)")
    ap.add_argument("--out", default=".", help="저장 폴더")
    ap.add_argument("--pc", action="store_true", help="blog.naver.com 주소로 출력 (기본: m.blog.naver.com)")
    ap.add_argument("--delay", type=float, default=0.5, help="페이지 요청 간격(초)")
    ap.add_argument("--hub-dir", help="링크 모음 사이트(index.html, sitemap.xml, robots.txt)를 만들 폴더")
    ap.add_argument("--site-url", default="", help="링크 모음 사이트 주소 (예: https://imwooha.github.io)")
    ap.add_argument("--blogger", action="append", default=[],
                    help="링크 모음에 함께 넣을 Blogger 주소 (여러 번 지정 가능, 예: https://zerisun.blogspot.com)")
    a = ap.parse_args()
    if a.hub_dir and not a.site_url:
        ap.error("--hub-dir 에는 --site-url 도 필요해요")

    blog_id = parse_blog_id(a.blog)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    host = "https://blog.naver.com" if a.pc else "https://m.blog.naver.com"
    home = f"{host}/{blog_id}"

    posts = collect(blog_id, a.delay)
    if not posts:
        sys.exit("가져온 글이 없어요.")
    for p in posts:
        p["url"] = f"{home}/{p['logNo']}"

    # 블로그 홈을 맨 앞에 넣고, 수정일은 가장 최근 글 날짜로
    latest = max((p["date"] for p in posts if p["date"]), default=None)
    entries = [(home, latest)] + [(p["url"], p["date"]) for p in posts]

    files = write_sitemaps(entries, out, blog_id)
    urls_txt = out / f"urls_{blog_id}.txt"
    urls_txt.write_text("\n".join(u for u, _ in entries) + "\n", encoding="utf-8")
    # 제목 / 링크 / 빈 줄 형식 (최신 글이 위)
    links_txt = out / f"links_{blog_id}.txt"
    links_txt.write_text("\n\n".join(f"{p['title']}\n{p['url']}" for p in posts) + "\n", encoding="utf-8")
    csv_path = out / f"posts_{blog_id}.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:  # 엑셀 한글 깨짐 방지
        w = csv.writer(f)
        w.writerow(["url", "title", "date"])
        for p in posts:
            w.writerow([p["url"], p["title"], p["date"] or p["rawDate"]])

    if a.hub_dir:
        sections = [{"name": "네이버 블로그", "home": home, "posts": posts}]
        for b in a.blogger:
            bposts = collect_blogger(b)
            bhome = re.sub(r"/sitemap\.xml$", "", b.rstrip("/"))
            sections.append({"name": "구글 블로그 (Blogger)", "home": bhome, "posts": bposts})
        write_hub(sections, Path(a.hub_dir), a.site_url)

    print(f"블로그 홈 + 글 {len(posts)}개 저장 완료:")
    for f in [*files, urls_txt, links_txt, csv_path]:
        print(f"  {f}")


if __name__ == "__main__":
    main()
