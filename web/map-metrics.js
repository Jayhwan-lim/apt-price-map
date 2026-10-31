/* Explicit map metric definitions. No asking-price data is inferred. */
(function(root){
  const definitions = {
    sale:['실거래가','선택 면적의 최근 3·6·12개월 실거래 평균. 직거래 설정 반영.'],
    pyeong:['평당가격','최근 실거래 평균 ÷ 공급면적 × 3.3058. 공급면적은 건축물대장 전유공용면적의 전용 + 주거공용(계단·승강기·벽체)입니다. ≈ 표시는 추정값입니다: 같은 단지 다른 평형의 공용면적 비율, 대장에 자료가 없는 단지는 같은 동·같은 연대 단지들의 공급/전용 비율 중앙값(없으면 구 단위)을 씁니다. 실제 값이 있는 단지로 맞춰 보면 오차 중앙값 0%, 절반이 ±3% 안입니다. 최근 12개월 거래가 없으면 마지막 거래 달 평균에 날짜를 붙여 씁니다.'],
    gap:['매매전세갭','같은 면적의 최근 매매 평균 − 최근 12개월 전세 보증금 중앙값(3건 이상). 1년 계약이 3건 미만이면 2년치를 쓰고 (2년)으로 표시합니다. 월세 계약은 제외합니다. ≈ 표시는 이 평형 전세 계약이 없어, 같은 단지 다른 평형의 전세가율(없으면 주변 같은 연대 단지 중앙값)로 추정한 값입니다.'],
    rentRatio:['전세가율','최근 12개월 전세 보증금 중앙값 ÷ 최근 매매 평균 × 100. 1년 계약이 3건 미만이면 2년치를 쓰고 (2년)으로 표시합니다. 월세 계약은 제외합니다. ≈ 표시는 같은 단지 다른 평형(없으면 주변 같은 연대 단지)의 전세가율로 추정한 값입니다. 다른 평형 기준 추정은 절반이 실제와 −7~+8% 안입니다.'],
    turnover:['거래회전율','최근 데이터 12개월의 단지 전체 매매 신고 건수 ÷ 세대수 × 100. 재거래도 각각 집계하며 직거래 설정을 반영합니다.'],
    units:['세대수','공동주택관리정보(K-apt) 세대수, 없으면 건축물대장(총괄표제부·표제부) 세대수. 둘 다 없으면 이 단지의 연간 거래 건수를 주변 같은 연대 단지의 세대당 거래 비율로 나눠 추정하고 ≈를 붙입니다(오차가 큽니다).'],
    occupancy:['입주시기','사용승인일 기준(K-apt, 없으면 건축물대장). 실제 입주 시작과 몇 달 차이가 날 수 있습니다.'],
    land:['대지지분','건축물대장 대지면적 × 평형 전용면적 ÷ 단지 전용면적 합계(K-apt)로 나눈 세대별 산정치. ≈ 표시는 추정값입니다: 공급면적 ÷ 용적률(공급면적이 없으면 전용 × 1.33), 여러 단지가 한 필지를 나눠 쓰거나 대장에 대지 정보가 없으면 같은 동·같은 연대 단지의 용적률 중앙값을 씁니다. 실제 값과 비교하면 단지 용적률을 쓴 추정은 보통 ±5% 안이고, 주변 용적률을 쓴 추정은 오차가 더 큽니다. 등기부 대지권과 다를 수 있습니다.'],
    landFar:['대지지분/용적률','세대별 대지지분 산정치와 건축물대장 용적률을 함께 표시합니다. ≈ 표시는 추정값입니다.'],
    far:['용적률','건축물대장 총괄표제부(없으면 표제부)의 용적률. 여러 단지가 한 필지를 나눠 쓰거나 대장 값이 없거나 범위를 벗어나면, 같은 동·같은 연대 단지들의 용적률 중앙값(없으면 구 단위)으로 추정하고 ≈를 붙입니다. 추정값은 실제와 크게 다를 수 있습니다.'],
    coverage:['건폐율','건축물대장 총괄표제부(없으면 표제부)의 건폐율. 범위를 벗어난 등록값은 표시하지 않습니다. ≈ 표시는 같은 동·같은 연대 단지의 건폐율 중앙값으로 추정한 값입니다.'],
    rank:['지역 순위','최근 12개월 실거래의 전용 3.3㎡당 가격으로 매긴 같은 구·같은 동 안의 순위. 거래가 3건 이상인 단지만 순위를 매깁니다. ≈ 표시는 최근 1년 거래가 1~2건이라 참고용인 순위입니다.'],
    rel:['평소 대비 상대가격','같은 구 안에서 이 단지가 차지하던 가격 위치의 변화. 전용 3.3㎡당 가격을 구 중앙값과 비교해, 지난해를 뺀 그 전 5년(연 3건 이상인 해 3개 이상) 평균 위치와 최근 12개월 위치를 비교합니다. 예: 평소 구 평균보다 30% 비쌌는데 지금 17% 비싸면 −10%. 새 아파트가 나이를 먹거나 주변에 새 단지가 들어서면 위치가 꾸준히 내려가는 경우가 많아, 일시적 열세인지는 따로 판단해야 합니다. 투자 추천이 아닙니다. ≈ 표시는 거래가 적어 연 1건 이상인 해까지 넣어 계산한 값입니다.'],
    peak:['전고점 대비','올해 이전 가장 높았던 해의 연 중앙값(거래 3건 이상)과 최근 실거래 평균을 비교합니다. 최근 3개월 안에 역대 최고가를 넘은 거래가 있으면 신고가로 표시합니다. ≈ 표시는 연 3건 이상인 해가 없어 거래가 적은 해(신축은 최근 3개월 전 가장 높은 달)를 기준으로 삼은 값입니다.'],
    vol:['거래 활발도','최근 3개월(이번 달 제외) 매매 건수를 그 전 36개월의 3개월 평균과 비교합니다.'],
    landPrice:['대지지분당 가격','최근 실거래 평균 ÷ 세대별 대지지분(평). 재건축 사업성을 볼 때 쓰는 지표입니다. ≈ 표시는 대지지분이 추정값이라는 뜻입니다(대지지분 설명 참고). 최근 12개월 거래가 없으면 마지막 거래 달 평균을 쓰고 (24.05 거래)처럼 날짜를 붙입니다.'],
    conv:['전월세 전환율','최근 12개월 월세 계약의 (월세 × 12) ÷ (같은 면적 전세 중앙값 − 월세 보증금) 중앙값. ≈ 표시는 이 단지 월세 계약이 부족해 같은 동·같은 연대 단지의 전환율 중앙값으로 추정한 값입니다.'],
    renew:['전세 갱신 인상률','최근 12개월 전세 갱신 계약의 종전 대비 보증금 인상률 중앙값과 계약갱신청구권 사용 비율. ≈ 표시는 이 단지 갱신 계약이 부족해 주변 같은 연대 단지의 중앙값으로 추정한 값입니다.'],
    park:['세대당 주차','K-apt 주차대수(지상+지하) ÷ 세대수. ≈ 표시는 K-apt에 없는 단지로, 같은 동·같은 연대 단지의 세대당 주차 중앙값으로 추정한 값입니다.'],
    subway:['지하철 도보','K-apt 공동주택관리정보에 등록된 지하철역까지 도보 시간. ≈ 표시는 K-apt에 없는 단지로, 카카오맵 기준 가장 가까운 지하철역까지 직선거리를 분당 70m로 나눠 추정한 시간입니다. K-apt 값이 있는 단지로 맞춰 보면 절반은 같은 구간, 열에 아홉은 한 구간 차이 안입니다.']
  };
  function value(metric,c,band,now,facts,variant){
    const price=now && now.avg;
    const money=p=>Math.abs(p)>=10000?(p/10000).toFixed(2).replace(/0$/,'').replace(/\.0$/,'')+'억':Math.round(p).toLocaleString('ko-KR')+'만원';
    const area=facts?.areas?.[band];
    const size=area?area+'㎡':band+'㎡형';
    const approx=(list)=>Array.isArray(list)&&list.includes(band)?'≈':'';
    if(metric==='sale')return price>0?size+' · '+money(price):'실거래 정보 없음';
    // No trade in the last 12 months: the last traded month, dated.
    const lastOf=()=>{const o=!(price>0)&&facts?.last?.[band];return o?{p:o[1],tag:' ('+String(o[0]).slice(2,4)+'.'+String(o[0]).slice(4)+' 거래)'}:null;};
    if(metric==='pyeong'){
      const sup=facts?.supply?.[band];if(!(sup>0))return '평당가 정보 없음';
      const o=lastOf(),p=price>0?price:o?o.p:0;if(!p)return '실거래 정보 없음';
      return '평당 '+approx(facts.supplyEst)+Math.round(p/sup*3.305785).toLocaleString('ko-KR')+'만원'+(o?o.tag:'');
    }
    const E=(flag)=>flag?'≈':'';
    if(metric==='units')return facts?.units>0?E(facts.unitsEst)+facts.units.toLocaleString('ko-KR')+'세대':'세대수 정보 없음';
    if(metric==='turnover')return facts?.units>0 && facts.trades12?'연 '+E(facts.unitsEst)+(facts.trades12[variant==='all'?1:0]/facts.units*100).toFixed(1)+'%':'회전율 정보 없음';
    const rent=facts?.rent?.[band];
    const long=Array.isArray(facts?.rentLong)&&facts.rentLong.includes(band)?' (2년)':'';
    const rE=E(Array.isArray(facts?.rentEst)&&facts.rentEst.includes(band));
    if(metric==='gap'||metric==='rentRatio'){
      // No sale in the last 12 months: the last traded month, dated.
      const o=lastOf(),p=price>0?price:o?o.p:0;
      if(!rent)return '전세 정보 없음';if(!p)return '실거래 정보 없음';
      return (metric==='gap'?'갭 '+rE+money(p-rent[0]):'전세가율 '+rE+Math.round(rent[0]/p*100)+'%')+long+(o?o.tag:'');
    }
    const land=facts?.land?.[band];
    const one=x=>(Math.round(x*10)/10).toString();
    const est=facts?.landEst?'≈':'';
    if(metric==='land')return land?est+one(land[1])+'평 ('+one(land[0])+'㎡)':'대지지분 정보 없음';
    const farTxt=()=>(facts.farEst?'≈':'')+facts.far.toFixed(facts.farEst?0:1)+'%';
    if(metric==='landFar')return land && facts?.far?est+one(land[1])+'평 · 용적률 '+farTxt():'정보 없음';
    if(metric==='far')return facts?.far?'용적률 '+farTxt():'용적률 정보 없음';
    if(metric==='coverage')return facts?.coverage?'건폐율 '+E(facts.coverageEst)+facts.coverage.toFixed(1)+'%':'건폐율 정보 없음';
    if(metric==='rank'){const r=facts?.rk;if(!r)return '최근 1년 거래 없음';return E(facts.rkEst)+[r[0]?'구 '+r[0]+'위':'',r[2]?'동 '+r[2]+'위':''].filter(Boolean).join(' · ');}
    if(metric==='rel'){const r=facts?.rv;if(!r)return facts?.trades12&&facts.trades12[1]>0?'비교 이력 부족(신축)':'최근 1년 거래 없음';const pc=x=>(x>=0?'+':'−')+Math.abs(Math.round(x))+'%';return '평소 대비 '+E(facts.rvEst)+pc(r[2])+' (구 평균 '+pc(r[0])+'→'+pc(r[1])+')';}
    if(metric==='peak'){
      const hi=facts?.high?.[band];
      if(hi)return '신고가 '+money(hi[1]);
      const pk=facts?.peak?.[band];
      if(!(price>0))return '실거래 정보 없음';
      if(!pk)return '이전 거래 없음';
      const pe=E(Array.isArray(facts.peakEst)&&facts.peakEst.includes(band));
      const r=price/pk[1]-1;return (r>=0?'전고점 돌파 '+pe+'+':'전고점 '+pe)+(r>=0?'':'−')+Math.abs(Math.round(r*100))+'%';
    }
    if(metric==='vol'){const v=facts?.vol;if(!v)return '거래 정보 없음';return v[1]>0?'평소의 '+(v[0]/v[1]).toFixed(1)+'배 ('+v[0]+'건)':'최근 3개월 '+v[0]+'건';}
    if(metric==='landPrice'){
      const l=facts?.land?.[band];if(!l)return '대지지분 정보 없음';
      const o=lastOf(),p=price>0?price:o?o.p:0;if(!p)return '실거래 정보 없음';
      return '대지 평당 '+(facts.landEst?'≈':'')+money(p/l[1])+(o?o.tag:'');
    }
    if(metric==='conv')return facts?.conv?'전환율 '+E(facts.convEst)+facts.conv.toFixed(1)+'%':'월세 정보 없음';
    if(metric==='renew'){const r=facts?.renew;return r?'갱신 '+E(facts.renewEst)+(r[1]>=0?'+':'')+r[1].toFixed(1)+'% · 청구권 '+r[2]+'%':'갱신 정보 없음';}
    if(metric==='park')return facts?.park?'세대당 '+E(facts.parkEst)+facts.park.toFixed(2)+'대':'주차 정보 없음';
    if(metric==='subway'){const t=facts?.sub;return t?(t[2]?t[2]+'역 ':'역 ')+E(facts.subEst)+t[0]:'지하철 정보 없음';}
    if(metric==='occupancy'){
      if(facts?.occ){const y=+facts.occ.slice(0,4), m=+facts.occ.slice(4,6);return y+'.'+String(m).padStart(2,'0')+' 사용승인';}
      return c.by?'건축 '+c.by+'년':'입주시기 정보 없음';
    }
    return '정보 없음';
  }
  root.MapMetrics={definitions,value};
  if(typeof module!=='undefined')module.exports=root.MapMetrics;
})(typeof window!=='undefined'?window:globalThis);
