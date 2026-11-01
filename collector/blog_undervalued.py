"""Draft the "지금 저평가 단지는?" post from the current map facts.

A complex qualifies when it was usually priced above its district median
(per 3.3 m2, the five full years before last year), its standing now
(last 12 months) is at least 10% lower than usual, and the numbers are
solid: no estimates, 10+ trades in the last 12 months, 300+ households.

Writes blog/posts/<date>-undervalued.md. The prose around the tables is a
template; the numbers come from web/data/map-metrics.json.
"""

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://geuttaeneolma.com/"
KST = timezone(timedelta(hours=9))


def load():
    facts = json.loads((ROOT / "web/data/map-metrics.json").read_text())["complexes"]
    data = json.loads((ROOT / "web/data/complexes.json").read_text())
    return facts, {c["key"]: c for c in data["complexes"]}, data


def pct(x):
    return f"{'+' if x >= 0 else '−'}{abs(x):.0f}%"


def main():
    facts, cx, data = load()
    last_year = int(str(data["mstart"])[:4]) + (int(str(data["mstart"])[4:]) - 1 + data["mcount"] - 1) // 12
    built = {k: (int(f["occ"][:4]) if f.get("occ") else cx[k].get("by")) for k, f in facts.items()}
    new_in = defaultdict(int)  # complexes completed in the last five years, per dong
    for k, c in cx.items():
        if built.get(k) and built[k] >= last_year - 5:
            new_in[(c["code"], c["umd"])] += 1

    rows = []
    for k, f in facts.items():
        rv, t = f.get("rv"), f.get("trades12") or [0, 0]
        if not rv or f.get("rvEst") or rv[0] < 0 or rv[2] > -10:
            continue
        if t[0] < 10 or (f.get("units") or 0) < 300 or f.get("unitsEst"):
            continue
        c = cx[k]
        rows.append({"k": k, "nm": c["nm"], "sido": c["sido"], "sgg": c["sgg"], "gu": c.get("gu") or "",
                     "umd": c["umd"], "usual": rv[0], "now": rv[1], "change": rv[2], "trades": t[0],
                     "units": f["units"], "built": built.get(k), "new": new_in[(c["code"], c["umd"])]})
    rows.sort(key=lambda r: r["change"])
    seoul = [r for r in rows if r["sido"].startswith("서울")]
    gyeonggi = [r for r in rows if not r["sido"].startswith("서울")]
    age = lambda r: last_year - r["built"] if r["built"] else None
    new_supply = [r for r in rows if r["new"] >= 5]
    old = [r for r in rows if age(r) is not None and age(r) >= 30]
    plain = [r for r in gyeonggi if r["new"] <= 2 and age(r) is not None and 5 <= age(r) < 30]
    by_city = Counter(r["sgg"] for r in rows).most_common(5)

    def link(r):
        return f"[{r['nm']}]({SITE}#k={quote(r['k'], safe='')})"

    def place(r):
        return " ".join(x for x in (r["sgg"], r["gu"], r["umd"]) if x)

    def table(items):
        out = ["| 단지 | 위치 | 평소 구 평균 대비 | 지금 | 변화 | 1년 거래 | 세대수 | 준공 |",
               "|---|---|---:|---:|---:|---:|---:|---:|"]
        for r in items:
            out.append(f"| {link(r)} | {place(r)} | {pct(r['usual'])} | {pct(r['now'])} | **{pct(r['change'])}** "
                       f"| {r['trades']}건 | {r['units']:,} | {r['built'] or '-'} |")
        return "\n".join(out)

    today = datetime.now(KST)
    window_end = f"{last_year}.{(int(str(data['mstart'])[4:]) - 1 + data['mcount'] - 1) % 12 + 1:02d}"
    slug = f"{today:%Y-%m}-undervalued"
    title = f"지금 '저평가' 단지는? 평소 몸값보다 내려온 아파트 ({today.year}년 {today.month}월)"
    usual_years = f"{last_year - 6}~{last_year - 2}년"
    city = by_city[0][0]
    city_rows = [r for r in rows if r["sgg"] == city]
    city_near_new = sum(1 for r in city_rows if r["new"] >= 1)
    city_built = sum(1 for k, c in cx.items() if c["sgg"] == city and built.get(k) and built[k] >= last_year - 5)
    top_s = seoul[0] if seoul else None
    busiest_s = max(seoul, key=lambda r: r["trades"]) if seoul else None
    top_g = plain[0] if plain else None
    body = f"""---
title: {title}
date: {today:%Y-%m-%d}
slug: {slug}
description: 평소엔 구 평균보다 비쌌는데 최근 1년 몸값이 10% 넘게 내려온 아파트를 서울·경기 1만 7천여 단지에서 직접 뽑아 봤다. {len(rows)}곳이 나왔고, 서울은 {len(seoul)}곳뿐이었다. 숫자를 그대로 믿으면 안 되는 이유까지 정리했다.
---

"저평가 단지"라는 말, 부동산 글에서 정말 자주 본다. 그런데 막상 기준을 물어보면 다 다르다. 누구는 평당가가 싸다는 뜻으로, 누구는 전고점보다 떨어졌다는 뜻으로 쓴다.

그래서 이번에는 기준을 하나만 정하고 직접 뽑아 봤다. **같은 구 안에서 그 단지가 평소 차지하던 가격 위치보다, 지금 얼마나 내려와 있는가.**

예를 들어 평소 구 평균보다 30% 비싸던 단지가 요즘은 17%만 비싸다면 "평소 대비 −10%"다. 집값이 떨어졌다는 얘기가 아니다. 주변보다 덜 올랐다는 얘기다. 이 차이를 헷갈리면 안 된다.

## 어떻게 골랐나

- **평소 위치**: {usual_years} 각 해의 전용 3.3㎡당 실거래 가격을 그해 구 중앙값과 비교해 평균을 냈다 (연 3건 이상 거래된 해가 3개 이상인 단지만)
- **지금 위치**: 최근 12개월({window_end}까지)을 같은 방식으로 계산했다
- **조건**: 평소 구 평균 이상이던 단지 중 지금 위치가 10% 이상 내려왔고, 최근 1년 거래 10건 이상, 300세대 이상
- 자료는 국토교통부 실거래가다. 그땐 얼마? 지도의 "평소 대비 상대가격" 탭과 같은 계산이다

거래가 적은 단지는 한두 건에 숫자가 크게 흔들려서 일부러 뺐다. 세대수나 가격을 추정값으로 채운 단지도 뺐다. 이런 글에서 추정치까지 섞으면 곤란하다고 봤다.

## 뽑아 보니 서울은 고작 {len(seoul)}곳

조건에 맞는 곳은 서울·경기를 합쳐 {len(rows)}곳이었다. 처음엔 서울에도 꽤 있을 줄 알았는데, 막상 돌려 보니 서울은 {len(seoul)}곳뿐이었다. 나머지 {len(gyeonggi)}곳은 전부 경기다.

{table(seoul)}

표를 보면서 가장 먼저 눈에 들어온 건 1위 {top_s['nm'] if top_s else ''}다. 평소 {top_s['sgg'] if top_s else ''} 안에서 평균보다 {pct(top_s['usual']) if top_s else ''} 위치에 있던 단지가 지금은 {pct(top_s['now']) if top_s else ''} 자리에 있다. 같은 구에 초고가 단지들이 몰려 있는 곳이라, 그쪽이 크게 오르면서 상대적으로 밀린 것 아닐까 싶다.

거래량으로 보면 {busiest_s['nm'] if busiest_s else ''}가 1년 {busiest_s['trades'] if busiest_s else ''}건으로 압도적이다. 거래가 이 정도 쌓인 단지는 숫자를 비교적 믿을 만하다. 반대로 10~20건대인 단지들은, 그 사이 어떤 평형이 주로 팔렸느냐에 따라 숫자가 꽤 달라질 수 있다는 점을 감안하고 봐야 한다.

전체적으로는 최근 1년 서울 핵심 지역이 워낙 크게 오르다 보니, 평소 구 안에서 위쪽에 있던 단지 몇 곳이 따라가지 못한 모습이다.

## 경기는 {by_city[0][0]}가 휩쓸었다, 그런데

경기는 결과를 보고 좀 놀랐다. {by_city[0][0]}만 {by_city[0][1]}곳이다. 그 뒤로 {", ".join(f"{c} {n}곳" for c, n in by_city[1:])} 순이다.

그런데 {city} 목록을 하나씩 짚어 보니 이유가 짐작됐다. {len(city_rows)}곳 중 {city_near_new}곳은 같은 동에 최근 5년 사이 지어진 단지가 있었다. {city} 전체로 보면 {last_year - 5}년 이후 준공한 단지만 {city_built}곳이다. 신축이 쏟아지면 같은 구 안의 가격 기준이 바뀌고, 기존 단지는 가만히 있어도 상대 위치가 내려간다. 이건 "잠시 열세"라기보다 구조가 바뀐 쪽에 가깝다고 본다. 실제로 같은 동에서 최근 5년 안에 지어진 단지가 5곳 이상인 후보가 {len(new_supply)}곳이었다.

그래서 경기는 한 번 더 걸렀다. **같은 동에 최근 5년 신축이 2곳 이하이고, 준공 5~29년인 단지**만 남겼다. 신축 공급과 재건축 기대라는 큰 변수 두 개를 걷어낸 목록이다. 개인적으로는 이쪽이 "일시적 열세"라는 말에 더 가까운 후보라고 생각한다. 남은 {len(plain)}곳 중 하락폭이 큰 15곳이다.

{table(plain[:15])}

{top_g['nm'] if top_g else ''}처럼 평소 구 평균 근처였던 단지가 지금 평균 아래로 내려간 경우도 있고, 평소 한참 위에 있다가 내려온 경우도 섞여 있다. 같은 −20%라도 출발점이 다르니 "평소 구 평균 대비" 칸을 같이 보는 게 좋다.

## 이 숫자를 그대로 믿으면 안 되는 이유

정리하면서 계속 마음에 걸렸던 것들이다.

1. **새 아파트는 원래 내려온다.** 입주 초기엔 신축 프리미엄으로 구 평균보다 한참 비싸다가, 해가 지나며 위치가 조금씩 내려오는 게 보통이다. 준공 10년 안쪽 단지의 하락은 상당 부분 이 효과일 수 있다.
2. **옆 동 신축은 못 걸렀다.** 이번엔 같은 동만 셌다. 바로 옆 동에 대단지가 입주한 경우는 위 목록에 그대로 남아 있을 수 있다.
3. **어떤 평형이 팔렸느냐.** 최근 1년 작은 평형 위주로 거래됐다면 3.3㎡당 가격이 평소와 달라 보인다.
4. **오래된 단지는 재건축 변수.** 준공 30년이 넘은 후보가 {len(old)}곳 있었다. 이런 곳은 사업 속도에 대한 기대가 가격 위치를 크게 움직인다.
5. **덜 올랐다는 게 오른다는 뜻은 아니다.** 이게 제일 중요하다. 상대 위치가 내려간 데는 대개 이유가 있고, 그 이유가 풀릴지는 이 숫자만으론 알 수 없다.

솔직히 이 목록은 "사야 할 단지"가 아니라 **"왜 그런지 한번 들여다볼 단지"**에 가깝다.

## 직접 찾아보는 법

[그땐 얼마? 지도]({SITE})에서 위쪽 필터의 **평소 대비** 버튼을 누르고 "−10~−20%"나 "−20% 이하"를 고른다. 그다음 **평소 구 평균보다 비쌌던 단지만**을 켜면 이 글과 같은 조건의 단지가 지도에 뜬다. 단지를 누르면 연도별 가격과, 같은 해 비슷한 가격이던 단지들이 그 뒤 어떻게 움직였는지 같이 볼 수 있다. 나도 이 글을 쓰면서 그 화면을 제일 많이 봤다.

다음 달에 같은 기준으로 다시 뽑아서, 목록이 어떻게 바뀌는지 비교해 볼 생각이다.

*공개된 실거래 자료를 정리한 글이며 투자 권유가 아니다. 거래 신고 지연과 해제로 숫자는 바뀔 수 있다.*
"""
    out = ROOT / "blog" / "posts" / f"{slug}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body)
    print(f"wrote {out.relative_to(ROOT)}: {len(rows)} complexes, Seoul {len(seoul)}, plain {len(plain)}")


if __name__ == "__main__":
    sys.exit(main())
