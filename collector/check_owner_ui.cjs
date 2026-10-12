const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('fs');
const assert = require('node:assert/strict');
(async () => {
  const browser = await chromium.launch({executablePath: process.env.CHROME_PATH || '/usr/bin/google-chrome', headless: true, args:['--no-sandbox']});
  const data = JSON.parse(fs.readFileSync('web/data/complexes.json'));
  const sample = {total:2, assigned:1, unknown:1, transactions:2, dongMissing:1,
    period:['20150101','20260901'], market:{price:100000,n:3,months:3,from:'2026-08',to:'2026-10'}, bins:[[80000,100000,0],[100000,120000,1]]};
  const fixture = {generated:data.generated, complexes:{'11710|잠실동|22':{inventoryDate:'2026-10-12',bands:{'27':{ex:sample,all:{...sample,assigned:2,unknown:0,bins:[[100000,120000,2]]}}}}}};
  fs.mkdirSync('/tmp/owner-ui', {recursive:true});
  for (const width of [1440,768,390]) {
    const context = await browser.newContext({viewport:{width,height:1000},hasTouch:width<1000,serviceWorkers:"block"});
    const page = await context.newPage();
    const errors=[]; page.on('pageerror', e=>errors.push(e.message));
    // Map fallback is deliberate: test the statistical UI independently of
    // Kakao's domain registration and network availability.
    await page.route('**/dapi.kakao.com/**', r=>r.abort());
    await page.route('**/data/owner-distributions.json', r=>r.fulfill({json:fixture}));
    await page.goto('http://127.0.0.1:8765/');
    await page.waitForFunction(()=>window.__aptMap && window.__aptMap.state.ready);
    await page.evaluate(()=>{const a=window.__aptMap;return a.selectComplex(a.state.byKey.get('11710|잠실동|22'),{band:'27'});});
    await page.locator('#owner-distribution-body .owner-row').first().waitFor().catch(async (error) => {
      console.log('STATE',await page.evaluate(()=>({band:__aptMap.state.band,variant:__aptMap.state.variant,body:document.getElementById('owner-distribution-body').innerHTML,hidden:document.getElementById('owner-distribution-section').hidden,classes:document.body.className})));
      await page.screenshot({path:'/tmp/owner-ui/failure.png',fullPage:true});throw error;
    });
    assert.match(await page.locator('#owner-distribution-body').innerText(), /추정 배정 약 1세대/);
    await page.evaluate(()=>{const x=document.getElementById('direct-toggle');x.checked=true;x.dispatchEvent(new Event('change'));});
    await page.waitForFunction(()=>document.getElementById('owner-distribution-body').textContent.includes('추정 배정 약 2세대'));
    assert.equal(await page.locator('#owner-distribution-section').count(),1);
    await page.locator('#owner-distribution-section h3').scrollIntoViewIfNeeded();
    await page.waitForTimeout(350);
    assert.ok(await page.locator('#owner-distribution-section h3').evaluate(el => {const r=el.getBoundingClientRect(); const at=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);return at===el || el.contains(at);}), 'Owner heading must be reachable by scrolling');
    await page.screenshot({path:`/tmp/owner-ui/fixture-${width}.png`});
    await page.evaluate(()=>{const x=document.getElementById('band-select');x.value='84';x.dispatchEvent(new Event('change'));});
    await page.waitForFunction(()=>document.getElementById('owner-distribution-body').textContent.includes('확인 중'));
    assert.equal(await page.locator('#owner-distribution-body .owner-row').count(),0);
    assert.equal(errors.length,0,errors.join('\n'));
    await context.close();
  }
  // The shipped payload must also render without fixture routing.
  if (fs.existsSync('web/data/owner-distributions.json')) {
    const page = await browser.newPage({viewport:{width:1440,height:1200}});
    await page.route('**/dapi.kakao.com/**', r=>r.abort());
    await page.goto('http://127.0.0.1:8765/');
    await page.waitForFunction(()=>window.__aptMap && window.__aptMap.state.ready);
    await page.evaluate(()=>{const a=window.__aptMap;return a.selectComplex(a.state.byKey.get('11710|잠실동|22'),{band:'27'});});
    await page.locator('#owner-distribution-body .owner-row').first().waitFor().catch(async (error) => {
      console.log('STATE',await page.evaluate(()=>({band:__aptMap.state.band,variant:__aptMap.state.variant,body:document.getElementById('owner-distribution-body').innerHTML,hidden:document.getElementById('owner-distribution-section').hidden,classes:document.body.className})));
      await page.screenshot({path:'/tmp/owner-ui/failure.png',fullPage:true});throw error;
    });
    console.log('Actual inventory UI:',await page.locator('#owner-distribution-body').innerText());
    await page.locator('#owner-distribution-section').screenshot({path:'/tmp/owner-ui/actual-ricenz.png'});
  }
  await browser.close();
  console.log('Owner distribution UI passed at desktop, tablet and phone widths');
})().catch(e=>{console.error(e);process.exit(1);});
