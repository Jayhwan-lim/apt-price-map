"""Build the 단지분석 blog into web/blog/ as plain static HTML.

Posts live in blog/posts/*.md with a small front matter block (title,
date, slug, description). Output, all crawlable without JavaScript:

    web/blog/index.html            list of posts
    web/blog/<slug>/index.html     one page per post
    web/blog/rss.xml               RSS 2.0 feed (for 네이버 서치어드바이저)
    web/sitemap.xml                site map (app page + blog)
    web/robots.txt                 points crawlers to the site map

Run after adding or editing a post, then commit web/.
"""

import html
import re
import sys
from datetime import datetime
from email.utils import format_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import markdown

ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "blog" / "posts"
OUT = ROOT / "web" / "blog"
SITE = "https://geuttaeneolma.com"
BLOG_NAME = "단지분석"
BLOG_DESC = "그땐 얼마?의 서울·경기 아파트 실거래가 데이터로 단지를 들여다보는 글"
KST = ZoneInfo("Asia/Seoul")
CSS_VERSION = "4"

# Coupang Partners side rails on post pages (inner 300x600, plus an
# outer 160x600 rail on very wide screens), same
# partner account as the map panel banner). Interim: the panel banner id
# rendered at sidebar size. When dedicated left/right banners are issued,
# swap the two codes in side_ad() — one place only.
COUPANG_TRACKING = "AF8973032"
COUPANG_BANNER_ID = 1037758
BANNER_INNER_LEFT = 1045614  # 블로그_안쪽1_가전디지털 (전용 발급, 2026-11-01)
BANNER_INNER_RIGHT = 1045618  # 블로그_안쪽2_고객관심기반추천 (전용 발급, 2026-11-02)
BANNER_OUTER_LEFT = 1045623  # 바깥좌 (전용 발급, 2026-11-02)
AD_NOTE = "이 게시물은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."


def side_ad(cls, width, banner_id):
    g = ('{"id":%d,"template":"carousel","trackingCode":"%s",'
         '"width":"%d","height":"600","tsource":""}'
         % (banner_id, COUPANG_TRACKING, width))
    return (f'    <aside class="side-ad {cls}" aria-label="광고">'
            '<div class="ad-slot-body">'
            '<script src="https://ads-partners.coupang.com/g.js"></script>'
            f'<script>new PartnersCoupang.G({g});</script></div>'
            f'<p class="ad-note">{AD_NOTE}</p></aside>\n')


def read_post(path):
    text = path.read_text()
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not m:
        raise SystemExit(f"{path}: missing front matter")
    meta = dict(line.split(": ", 1) for line in m.group(1).splitlines() if ": " in line)
    for field in ("title", "date", "slug", "description"):
        if not meta.get(field):
            raise SystemExit(f"{path}: front matter needs {field}")
    body = markdown.markdown(text[m.end():], extensions=["tables"], output_format="html")
    # Tables scroll sideways on phones instead of widening the page.
    body = body.replace("<table>", '<div class="table-wrap"><table>').replace("</table>", "</table></div>")
    meta["html"] = body
    meta["url"] = f"{SITE}/blog/{meta['slug']}/"
    meta["when"] = datetime.strptime(meta["date"], "%Y-%m-%d").replace(tzinfo=KST)
    return meta


def page(title, description, canonical, content, kind="website", extra_head=""):
    e = html.escape
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{e(title)}</title>
  <meta name="description" content="{e(description)}">
  <link rel="canonical" href="{canonical}">
  <meta property="og:type" content="{kind}">
  <meta property="og:url" content="{canonical}">
  <meta property="og:title" content="{e(title)}">
  <meta property="og:description" content="{e(description)}">
  <meta property="og:site_name" content="그땐 얼마?">
  <meta property="og:locale" content="ko_KR">
  <link rel="alternate" type="application/rss+xml" title="{BLOG_NAME}" href="{SITE}/blog/rss.xml">
  <link rel="icon" href="/icon.svg" type="image/svg+xml">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;600;700&display=swap">
  <link rel="stylesheet" href="/blog/blog.css?v={CSS_VERSION}">
{extra_head}</head>
<body>
  <header class="site-head">
    <a class="home" href="/">그땐 얼마?</a>
    <nav><a href="/blog/">{BLOG_NAME}</a><a href="/">지도에서 보기</a></nav>
  </header>
  <main>
{content}
  </main>
  <footer class="site-foot">
    <p>자료: 국토교통부 아파트 매매·전월세 실거래가, 건축물대장, 공동주택관리정보(공공데이터포털). 투자 권유가 아닙니다.</p>
    <p><a href="/">그땐 얼마? 지도</a> · <a href="/blog/rss.xml">RSS</a> · <a href="/privacy.html">개인정보처리방침</a></p>
  </footer>
</body>
</html>
"""


def main():
    posts = sorted((read_post(p) for p in POSTS.glob("*.md")), key=lambda p: p["date"], reverse=True)
    e = html.escape
    for p in posts:
        ld = ('  <script type="application/ld+json">{"@context":"https://schema.org","@type":"Article",'
              f'"headline":{_json(p["title"])},"datePublished":"{p["date"]}","dateModified":"{p["date"]}",'
              f'"description":{_json(p["description"])},"mainEntityOfPage":"{p["url"]}",'
              '"author":{"@type":"Organization","name":"그땐 얼마?"},'
              '"publisher":{"@type":"Organization","name":"그땐 얼마?"}}</script>\n')
        content = (f'    <article class="post">\n      <p class="crumb"><a href="/blog/">{BLOG_NAME}</a></p>\n'
                   f'      <h1>{e(p["title"])}</h1>\n      <p class="meta"><time datetime="{p["date"]}">'
                   f'{p["when"].year}년 {p["when"].month}월 {p["when"].day}일</time></p>\n'
                   f'{p["html"]}\n    </article>\n'
                   + side_ad("side-left", 300, BANNER_INNER_LEFT)
                   + side_ad("side-right", 300, BANNER_INNER_RIGHT)
                   + side_ad("side-left-outer", 160, BANNER_OUTER_LEFT)
                   + side_ad("side-right-outer", 160, COUPANG_BANNER_ID))
        target = OUT / p["slug"] / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page(f'{p["title"]} | {BLOG_NAME}', p["description"], p["url"], content, "article", ld))

    items = "\n".join(
        f'      <li><a href="/blog/{p["slug"]}/"><h2>{e(p["title"])}</h2></a>'
        f'<p class="meta"><time datetime="{p["date"]}">{p["date"].replace("-", ".")}</time></p>'
        f'<p>{e(p["description"])}</p></li>' for p in posts)
    index = (f'    <section class="list">\n      <h1>{BLOG_NAME}</h1>\n      <p class="lead">{e(BLOG_DESC)}</p>\n'
             f'      <ul class="posts">\n{items}\n      </ul>\n    </section>')
    (OUT / "index.html").write_text(page(f"{BLOG_NAME} | 그땐 얼마?", BLOG_DESC, f"{SITE}/blog/", index))

    rss_items = "\n".join(
        f"    <item><title>{e(p['title'])}</title><link>{p['url']}</link><guid>{p['url']}</guid>"
        f"<pubDate>{format_datetime(p['when'])}</pubDate><description>{e(p['description'])}</description></item>"
        for p in posts)
    (OUT / "rss.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0">\n  <channel>\n'
        f"    <title>{BLOG_NAME} | 그땐 얼마?</title>\n    <link>{SITE}/blog/</link>\n"
        f"    <description>{e(BLOG_DESC)}</description>\n    <language>ko</language>\n{rss_items}\n"
        "  </channel>\n</rss>\n")

    latest = posts[0]["date"] if posts else datetime.now(KST).strftime("%Y-%m-%d")
    urls = [(f"{SITE}/", None), (f"{SITE}/blog/", latest)] + [(p["url"], p["date"]) for p in posts]
    (ROOT / "web" / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(f"  <url><loc>{u}</loc>" + (f"<lastmod>{d}</lastmod>" if d else "") + "</url>" for u, d in urls)
        + "\n</urlset>\n")
    (ROOT / "web" / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\n")
    print(f"blog: {len(posts)} posts")


def _json(s):
    import json
    return json.dumps(s, ensure_ascii=False)


if __name__ == "__main__":
    sys.exit(main())
