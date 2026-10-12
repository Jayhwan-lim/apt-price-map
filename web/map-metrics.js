/* Explicit map metric definitions. No asking-price or lease data is inferred. */
(function(root){
  const definitions = {
    sale:['실거래가','선택 면적의 최근 3·6·12개월 실거래 평균. 직거래 설정 반영.'],
    asking:['매물가격','매도 호가 원자료 미연결. 실거래가로 대체하지 않습니다.'],
    pyeong:['평당가격','최근 실거래 평균 ÷ 대표 전용면적 × 3.305785. 공급면적 기준 평당가와 다릅니다.'],
    gap:['매매전세갭','같은 면적·기준일의 매매 및 전세 자료가 필요합니다. 전세 자료 미연결.'],
    rentRatio:['전세가율','같은 면적·기준일 전세가 ÷ 매매가 × 100. 전세 자료 미연결.'],
    turnover:['거래회전율','최근 데이터 12개월의 단지 전체 매매 신고 건수 ÷ 확인 세대수 × 100. 재거래도 각각 집계하며 직거래 설정을 반영합니다.'],
    units:['세대수','건축물대장과 면적별 외부 대조를 통과한 단지 전체 세대수. 미확인 단지는 정보 없음.'],
    occupancy:['입주시기','입주일 원자료 미연결. 실거래 자료의 건축연도를 구분해 표시합니다.'],
    land:['대지지분','선택 면적의 등기·대장상 전유세대 대지권 지분 자료가 필요합니다. 단지 대지면적을 세대수로 나누어 대신 표시하지 않습니다.'],
    landFar:['대지지분/용적률','전유세대 대지지분과 단지 용적률을 함께 표시하는 항목입니다. 원자료 미연결.'],
    far:['용적률','건축물대장상 단지 용적률 자료 미연결.'],
    coverage:['건폐율','건축물대장상 단지 건폐율 자료 미연결.']
  };
  function value(metric,c,band,now,facts,variant){
    const price=now && now.avg;
    const money=p=>p>=10000?(p/10000).toFixed(2).replace(/0$/,'').replace(/\.0$/,'')+'억':Math.round(p).toLocaleString('ko-KR')+'만원';
    const area=facts?.areas?.[band];
    const size=area?area+'㎡':band+'㎡형';
    if(metric==='sale')return price>0?size+' · '+money(price):'실거래 정보 없음';
    if(metric==='pyeong')return price>0 && area>0?'평당 '+Math.round(price/area*3.305785).toLocaleString('ko-KR')+'만원':'평당가 정보 없음';
    if(metric==='units')return facts?.units>0?facts.units.toLocaleString('ko-KR')+'세대':'세대수 정보 없음';
    if(metric==='turnover')return facts?.units>0 && facts.trades12?'연 '+(facts.trades12[variant==='all'?1:0]/facts.units*100).toFixed(1)+'%':'회전율 정보 없음';
    if(metric==='occupancy')return c.by?'건축 '+c.by+'년 · 입주 미확인':'입주시기 정보 없음';
    return '정보 없음';
  }
  root.MapMetrics={definitions,value};
  if(typeof module!=='undefined')module.exports=root.MapMetrics;
})(typeof window!=='undefined'?window:globalThis);
