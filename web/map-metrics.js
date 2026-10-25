/* Explicit map metric definitions. No asking-price data is inferred. */
(function(root){
  const definitions = {
    sale:['실거래가','선택 면적의 최근 3·6·12개월 실거래 평균. 직거래 설정 반영.'],
    pyeong:['평당가격','최근 실거래 평균 ÷ 공급면적 × 3.3058. 공급면적은 건축물대장 전유공용면적의 전용 + 주거공용(계단·승강기·벽체)입니다. ≈ 표시는 같은 단지 다른 평형의 공용면적 비율로 추정한 값입니다.'],
    gap:['매매전세갭','같은 면적의 최근 매매 평균 − 최근 12개월 전세 보증금 중앙값(3건 이상). 월세 계약은 제외합니다.'],
    rentRatio:['전세가율','최근 12개월 전세 보증금 중앙값 ÷ 최근 매매 평균 × 100. 월세 계약은 제외합니다.'],
    turnover:['거래회전율','최근 데이터 12개월의 단지 전체 매매 신고 건수 ÷ 세대수 × 100. 재거래도 각각 집계하며 직거래 설정을 반영합니다.'],
    units:['세대수','공동주택관리정보(K-apt) 세대수, 없으면 건축물대장(총괄표제부·표제부) 세대수.'],
    occupancy:['입주시기','사용승인일 기준(K-apt, 없으면 건축물대장). 실제 입주 시작과 몇 달 차이가 날 수 있습니다.'],
    land:['대지지분','건축물대장 대지면적 × 평형 전용면적 ÷ 단지 전용면적 합계(K-apt)로 나눈 세대별 산정치. ≈ 표시는 공급면적 ÷ 용적률로 추정한 값이며, 등기부 대지권과 다를 수 있습니다.'],
    landFar:['대지지분/용적률','세대별 대지지분 산정치와 건축물대장 용적률을 함께 표시합니다.'],
    far:['용적률','건축물대장 총괄표제부(없으면 표제부)의 용적률. 범위를 벗어난 등록값은 표시하지 않습니다.'],
    coverage:['건폐율','건축물대장 총괄표제부(없으면 표제부)의 건폐율. 범위를 벗어난 등록값은 표시하지 않습니다.']
  };
  function value(metric,c,band,now,facts,variant){
    const price=now && now.avg;
    const money=p=>Math.abs(p)>=10000?(p/10000).toFixed(2).replace(/0$/,'').replace(/\.0$/,'')+'억':Math.round(p).toLocaleString('ko-KR')+'만원';
    const area=facts?.areas?.[band];
    const size=area?area+'㎡':band+'㎡형';
    const approx=(list)=>Array.isArray(list)&&list.includes(band)?'≈':'';
    if(metric==='sale')return price>0?size+' · '+money(price):'실거래 정보 없음';
    if(metric==='pyeong'){const sup=facts?.supply?.[band];return price>0 && sup>0?'평당 '+approx(facts.supplyEst)+Math.round(price/sup*3.305785).toLocaleString('ko-KR')+'만원':'평당가 정보 없음';}
    if(metric==='units')return facts?.units>0?facts.units.toLocaleString('ko-KR')+'세대':'세대수 정보 없음';
    if(metric==='turnover')return facts?.units>0 && facts.trades12?'연 '+(facts.trades12[variant==='all'?1:0]/facts.units*100).toFixed(1)+'%':'회전율 정보 없음';
    const rent=facts?.rent?.[band];
    if(metric==='gap')return rent && price>0?'갭 '+money(price-rent[0]):'전세 정보 없음';
    if(metric==='rentRatio')return rent && price>0?'전세가율 '+Math.round(rent[0]/price*100)+'%':'전세 정보 없음';
    const land=facts?.land?.[band];
    const one=x=>(Math.round(x*10)/10).toString();
    const est=facts?.landEst?'≈':'';
    if(metric==='land')return land?est+one(land[1])+'평 ('+one(land[0])+'㎡)':'대지지분 정보 없음';
    if(metric==='landFar')return land && facts?.far?est+one(land[1])+'평 · 용적률 '+facts.far.toFixed(1)+'%':'정보 없음';
    if(metric==='far')return facts?.far?'용적률 '+facts.far.toFixed(1)+'%':'용적률 정보 없음';
    if(metric==='coverage')return facts?.coverage?'건폐율 '+facts.coverage.toFixed(1)+'%':'건폐율 정보 없음';
    if(metric==='occupancy'){
      if(facts?.occ){const y=+facts.occ.slice(0,4), m=+facts.occ.slice(4,6);return y+'.'+String(m).padStart(2,'0')+' 사용승인';}
      return c.by?'건축 '+c.by+'년':'입주시기 정보 없음';
    }
    return '정보 없음';
  }
  root.MapMetrics={definitions,value};
  if(typeof module!=='undefined')module.exports=root.MapMetrics;
})(typeof window!=='undefined'?window:globalThis);
