const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
 for(const width of [1440,768,390]){
  const context=await browser.newContext({viewport:{width,height:900},hasTouch:width<1000,serviceWorkers:'block'});
  const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/dapi.kakao.com/**',r=>r.abort());
  await page.goto('http://127.0.0.1:8765/');await page.waitForFunction(()=>window.__aptMap?.state.ready);
  assert.equal(await page.locator('#map-metric-select option').count(),12);
  await page.selectOption('#map-metric-select','units');
  await page.waitForFunction(()=>window.__aptMap.state.mapFacts);
  for(const metric of ['sale','asking','pyeong','gap','rentRatio','turnover','units','occupancy','land','landFar','far','coverage']){
   await page.selectOption('#map-metric-select',metric);
   const text=await page.evaluate(()=>__aptMap.mapMetricText(__aptMap.state.byKey.get('11710|신천동|17'),'35'));
   assert.ok(text.length>0);
   if(metric==='units')assert.equal(text,'6,864세대');
   if(['asking','gap','rentRatio'].includes(metric))assert.equal(text,'정보 없음');
   if(metric==='land')assert.equal(text,'5평 (16.5㎡)');
   if(metric==='far')assert.equal(text,'용적률 283.6%');
  }
  await page.selectOption('#map-metric-select','sale');
  await page.evaluate(()=>{
   window.kakao={maps:{CustomOverlay:function(options){this.options=options;},LatLng:function(){},event:{}}};
   const node=__aptMap.makeMapPin(__aptMap.state.byKey.get('11710|신천동|17'),'bg',null,'35').options.content;
   node.id='metric-test-pin';node.style.cssText='position:absolute;top:160px;left:25px;z-index:80';document.querySelector('.map-wrap').appendChild(node);
  });
  const name=await page.locator('#metric-test-pin .n').boundingBox();const value=await page.locator('#metric-test-pin .v').boundingBox();assert.ok(value.y>=name.y+name.height-1);
  const select=await page.locator('#map-metric-select').boundingBox();assert.ok(select.x>=0 && select.x+select.width<=width);
  await page.screenshot({path:'/tmp/owner-ui/map-metric-'+width+'.png'});
  assert.deepEqual(errors,[]);await context.close();
 }
 await browser.close();console.log('Map metric controls and two-line pins passed at three viewport widths');
})().catch(e=>{console.error(e);process.exit(1)});
