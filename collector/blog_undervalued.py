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
    body = f"""---
title: {title}
date: {today:%Y-%m-%d}
slug: {slug}
description: 서울·경기 아파트 1만 7천여 곳 중 평소엔 구 평균보다 비쌌는데 최근 1년 몸값이 10% 넘게 내려온 {len(rows)}곳. 숫자로 고른 후보와, 그 숫자를 그대로 믿으면 안 되는 이유까지 정리했습니다.
---

"저평가 단지"라는 말은 흔히 쓰이지만 기준이 제각각입니다. 이 글에서는 하나의 기준만 씁니다. **같은 구 안에서 그 단지가 평소 차지하던 가격 위치보다, 지금 얼마나 내려와 있는가**입니다.

예를 들어 평소 구 평균보다 30% 비싸던 단지가 요즘은 17%만 비싸다면, 이 단지는 "평소 대비 −10%"입니다. 집값이 떨어졌다는 뜻이 아니라, 주변보다 덜 올랐다는 뜻입니다.

## 어떻게 골랐나

- **평소 위치**: {usual_years} 각 해의 전용 3.3㎡당 실거래 가격을 그해 구 중앙값과 비교한 평균 (연 3건 이상인 해 3개 이상)
- **지금 위치**: 최근 12개월({window_end}까지) 같은 방식
- **조건**: 평소 구 평균 이상이던 단지 중 지금 위치가 10% 이상 내려왔고, 최근 1년 거래 10건 이상, 300세대 이상
- 자료: 국토교통부 실거래가 (그땐 얼마? 지도의 "평소 대비 상대가격" 탭과 같은 계산)

이 조건에 맞는 곳은 서울·경기 {len(rows)}곳입니다. 서울은 {len(seoul)}곳뿐이고 나머지 {len(gyeonggi)}곳이 경기입니다. 지역별로는 {", ".join(f"{c} {n}곳" for c, n in by_city)} 순으로 많습니다.

## 서울 {len(seoul)}곳

{table(seoul)}

서울에서는 최근 1년 핵심 지역이 크게 오르면서, 평소 구 안에서 상위권이던 단지 중 일부가 상대적으로 덜 오른 경우가 보입니다. 거래가 10~30건 수준인 곳이 많아, 어떤 평형이 주로 거래됐는지에 따라 숫자가 흔들릴 수 있습니다.

## 경기: 숫자만 보면 {by_city[0][0]}가 압도적

경기 상위권은 {by_city[0][0]} 단지가 많이 차지합니다. 다만 이런 경우는 "잠시 열세"라기보다 **주변에 새 아파트가 대거 들어서면서 기존 단지의 상대 위치가 내려간** 경우일 가능성이 큽니다. 같은 동에서 최근 5년 안에 지어진 단지가 5곳 이상인 후보가 전체 {len(rows)}곳 중 {len(new_supply)}곳입니다.

그래서 경기는 **주변(같은 동)에 최근 5년 신축이 2곳 이하이고, 준공 5~29년**인 단지만 따로 추려 봤습니다. 신축 공급과 재건축 기대라는 큰 변수 두 개를 걷어낸 목록이라, "일시적 열세"에 더 가까운 후보입니다. 해당 {len(plain)}곳 중 하락폭 상위 15곳입니다.

{table(plain[:15])}

## 이 숫자를 그대로 믿으면 안 되는 이유

1. **새 아파트는 원래 내려옵니다.** 입주 초기에는 신축 프리미엄으로 구 평균보다 크게 비싸다가, 해가 지나며 위치가 조금씩 내려오는 게 일반적입니다. 준공 10년 안쪽 단지의 하락은 이 효과일 수 있습니다.
2. **주변 신축 공급.** 바로 옆 동에 대단지가 입주하면 같은 구 안의 기준이 바뀝니다. 이 글은 같은 동만 셌기 때문에 옆 동 공급은 걸러지지 않았습니다.
3. **거래 평형 구성.** 최근 1년에 작은 평형만 거래됐다면 3.3㎡당 가격이 평소와 달라 보일 수 있습니다.
4. **오래된 단지({len(old)}곳)는 재건축 기대**의 변화가 가격 위치를 크게 움직입니다. 사업 지연 같은 소식이 반영된 결과일 수 있습니다.
5. **"덜 올랐다"는 사실이 "앞으로 오른다"는 뜻은 아닙니다.** 상대 위치가 내려간 데에는 대개 이유가 있고, 그 이유가 해소될지는 이 숫자만으로 알 수 없습니다.

## 직접 찾아보기

[그땐 얼마? 지도]({SITE})에서 위쪽 필터의 **평소 대비** 버튼을 누르고 "−10~−20%"나 "−20% 이하"를 고른 뒤 **평소 구 평균보다 비쌌던 단지만**을 켜면, 이 글과 같은 조건의 단지가 지도에 표시됩니다. 단지를 누르면 연도별 가격과 같은 해 비슷한 가격이던 단지들의 흐름을 비교할 수 있습니다.

*이 글은 공개된 실거래 자료를 정리한 것이며 투자 권유가 아닙니다. 거래 신고 지연과 해제로 숫자는 바뀔 수 있습니다.*
"""
    out = ROOT / "blog" / "posts" / f"{slug}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body)
    print(f"wrote {out.relative_to(ROOT)}: {len(rows)} complexes, Seoul {len(seoul)}, plain {len(plain)}")


if __name__ == "__main__":
    sys.exit(main())
