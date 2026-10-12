"""Record public-output comparisons, not owner-level accuracy or fitted parameters."""
import argparse
import json
import urllib.request
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
import statistics
from owner_distribution import estimate
from audit_unit_models import audit

ROOT = Path(__file__).resolve().parent.parent
TARGETS = {'11710|잠실동|22': '11710-6249', '11710|신천동|17': '11710-6266',
           '11710|잠실동|19': '11710-6346'}


def snapshot(payload, url):
    return {'source': url, 'observed': datetime.now(timezone.utc).isoformat(),
            'marketAsof': payload.get('marketAsof'), 'areas': [
                {'area': a['area'], 'total': a['total'], 'assigned': a['counts']['trade'],
                 'unknown': a['unknown'], 'market': {k: a.get('market', {}).get(k)
                     for k in ('price', 'n', 'months', 'until')},
                 'bins': [[b['from'], b['to'], b['trade']] for b in a['bins']]}
                for a in payload['byArea']]}


def compare(entries, peers):
    web = ROOT / 'web/data'
    data = json.loads((web / 'complexes.json').read_text())
    results = []
    for entry in entries:
        c = next(c for c in data['complexes'] if c['key'] == entry['complex_key'])
        types = json.loads((web / f"region/{c['code']}.json").read_text())['c'][str(c['id'])]['ty']
        rows = json.loads((web / f"trades/{c['code']}.json").read_text())['complexes'][str(c['id'])]
        peer = peers[c['key']]
        for band in entry.get('publish_bands', entry.get('area_counts', {})):
            own = estimate(rows, entry['pools'], band, types, data['generated'])
            inclusive = estimate(rows, entry['pools'], band, types, data['generated'], True)
            assert own == estimate(rows[::-1], entry['pools'], band, types, data['generated'])
            lo, hi = types[band][:2]
            matches = [p for p in peer['areas'] if lo - .05 <= p['area'] <= hi + .05]
            if len(matches) > 1:
                raise ValueError('ambiguous external area mapping')
            p = matches[0] if matches else None
            if p and own['total'] != p['total']:
                raise ValueError(f"{c['key']} {band}: external household count mismatch")
            ob = {(a,b): n for a,b,n in own['bins']}
            pb = {(a,b): n for a,b,n in p['bins']} if p else {}
            diff = [[a,b,ob.get((a,b),0),pb.get((a,b),0),ob.get((a,b),0)-pb.get((a,b),0)]
                    for a,b in sorted(ob.keys() | pb.keys())] if p else []
            years = defaultdict(list)
            for r in rows:
                if lo-.01 <= r[1] <= hi+.01 and not r[4] and not r[5] and r[3]>0:
                    years[r[0][:4]].append(r[3])
            med = {y: statistics.median(v) for y,v in years.items() if len(v)>=5}
            filtered = [r for r in rows if not lo-.01<=r[1]<=hi+.01 or r[0][:4] not in med
                        or .5*med[r[0][:4]] <= r[3] <= 2*med[r[0][:4]]]
            scenarios = {'baseline': own, 'direct_included': inclusive,
                'annual_half_double_screen': estimate(filtered,entry['pools'],band,types,data['generated']),
                'all_dong_hidden': estimate([r[:6]+[''] for r in rows],entry['pools'],band,types,data['generated'])}
            if peer.get('marketAsof'):
                for name, direct in [('asof_peer',False),('asof_peer_direct_included',True)]:
                    scenarios[name] = estimate(rows,entry['pools'],band,types,peer['marketAsof'],direct)
            results.append({'complex_key':c['key'],'name':c['nm'],'band':band,
                'generated':data['generated'],'peer':p,'peer_observed':peer['observed'],
                'peer_status':'observed' if p else 'no matching displayed area',
                'unmatched':0,'reproducible':True,'scenarios':scenarios,
                'bin_difference':diff,'bin_count_L1':sum(abs(d[4]) for d in diff) if p else None,
                'sensitivity_reference':audit(rows,entry['pools'],band,types)})
    return results


def report(results):
    lines=['# 소유주 매수가 모형 정합성 대조', '',
        '상대 공개 설명: https://ulma.site/about/ · 원본/관측일: owner-peer-snapshots.json.',
        '모형 v1의 정합성 비교이며 소유주별 정확도 검증이 아니다. 단위: 가격 만원, 분포 세대.',
        'L1 = 동일 2억원 구간별 배정 수 차이 절댓값 합(미배정 제외). 참고 지표이며 공개 차단 기준이 아니다.', '',
        '|단지·면적|세대수|우리 배정/미배정|상대 배정/미배정|L1|우리/상대 중앙값(억)|',
        '|---|---:|---:|---:|---:|---:|']
    for r in results:
        b=r['scenarios']['baseline']; p=r['peer']
        price=lambda x: str(x['market']['price']/10000) if x and x.get('market') and x['market'].get('price') else '없음'
        lines.append(f"|{r['name']} {r['band']}㎡|{b['total']}|{b['assigned']}/{b['unknown']}|"+
            (f"{p['assigned']}/{p['unknown']}" if p else '해당 면적 표시 없음')+
            f"|{r['bin_count_L1']}|{price(b)}/{price(p)}|")
    for r in results:
        lines += ['',f"## {r['name']} {r['band']}㎡",'',
            f"우리 기준: {r['generated']}; 상대 관측: {r['peer_observed']}; 상대 가격 기준: {(r['peer'] or {}).get('market',{}).get('until')}",
            'unmatched=0 (직거래 제외·포함 모두); 역순 입력 재계산 동일. 세대수는 위 표의 양측 수치 일치.', '',
            '|구간(억, 하한 포함·상한 제외)|우리|상대|우리−상대|','|---|---:|---:|---:|']
        lines += [f'|{a/10000:g}–{b/10000:g}|{o}|{p}|{d:+d}|' for a,b,o,p,d in r['bin_difference']]
        lines += ['', '|실험 가정|배정|미배정|유효 거래|중앙값(억)|','|---|---:|---:|---:|---:|']
        for name,s in r['scenarios'].items():
            lines.append(f"|{name}|{s['assigned']}|{s['unknown']}|{s['transactions']}|{s['market']['price']/10000 if s['market'] else '없음'}|")
        a=r['sensitivity_reference']
        lines += ['', '|참고 모형|선택 건수|중앙값(만원)|','|---|---:|---:|']
        lines += [f"|{k}|{a[k]['selected']}|{a[k]['median_manwon']}|" for k in ['F_all','F_known','D_known']]
    return '\n'.join(lines)+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh',action='store_true')
    args=parser.parse_args()
    dest=ROOT/'docs/owner-peer-snapshots.json'
    peers=json.loads(dest.read_text()) if dest.exists() else {}
    entries=json.loads((ROOT/'data/owner_inventory.json').read_text())
    if args.refresh:
        # A failed request is not evidence that the competitor has no display.
        # Finish every request/computation before overwriting the last report.
        for entry in entries:
            ck=entry['complex_key']; url='https://ulma.site/api/apt/'+TARGETS[ck]
            request=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
            with urllib.request.urlopen(request,timeout=40) as response:
                peers[ck]=snapshot(json.load(response),url)
    results=compare(entries,peers)
    dest.write_text(json.dumps(peers,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'docs/owner-comparison-latest.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'docs/owner-comparison-latest.md').write_text(report(results))
    print('Recorded comparisons:',len(results))


if __name__=='__main__':
    main()
