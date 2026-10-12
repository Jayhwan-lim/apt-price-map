"""Map facts derived from the same transaction snapshot; no listing estimates."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def build():
    web=ROOT/'web/data'
    data=json.loads((web/'complexes.json').read_text())
    owners=json.loads((web/'owner-distributions.json').read_text())
    verified=owners['complexes'] if owners.get('generated')==data['generated'] else {}
    inventory={e["complex_key"]:e for e in json.loads((ROOT/"data/owner_inventory.json").read_text())}
    try:
        land=json.loads((ROOT/'data/land_facts.json').read_text())
    except Exception:
        land={}
    regions={}
    out={}
    for c in data['complexes']:
        code=c['code']
        if code not in regions:
            regions[code]=json.loads((web/f'region/{code}.json').read_text())['c']
        rec=regions[code].get(str(c['id']),{})
        facts={'areas':{b:t[2] for b,t in rec.get('ty',{}).items()}}
        entry=verified.get(c['key'])
        if entry and sum(v['ex']['total'] for v in entry['bands'].values()) == inventory[c['key']]['expected_units']:
            facts['units']=sum(v['ex']['total'] for v in entry['bands'].values())
            totals=[0,0]
            for series in rec.get('m',{}).values():
                ex={series['e'][i]:series['e'][i+1] for i in range(0,len(series['e']),3)}
                all_=dict(ex)
                a=series.get('a',[])
                all_.update({a[i]:a[i+1] for i in range(0,len(a),3)})
                for j,counts in enumerate((ex,all_)):
                    totals[j]+=sum(n for mi,n in counts.items() if data['mcount']-12<=mi<data['mcount'])
            facts['trades12']=totals
        lf=land.get(c['key'])
        if lf:
            facts['land']=lf['land']; facts['far']=lf['far']; facts['coverage']=lf['coverage']
        out[c['key']]=facts
    target=web/'map-metrics.json'
    tmp=target.with_suffix('.tmp')
    tmp.write_text(json.dumps({'generated':data['generated'],'complexes':out},ensure_ascii=False,separators=(',',':')))
    tmp.replace(target)


if __name__=='__main__':
    build()
