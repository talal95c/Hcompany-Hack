import {chromium} from 'playwright';
import {mkdir} from 'node:fs/promises';
const browser=await chromium.connectOverCDP('http://localhost:29229');
const context=await browser.newContext({viewport:{width:1920,height:1080},deviceScaleFactor:1,reducedMotion:'reduce'});
const page=await context.newPage();
const errors=[];
page.on('pageerror', e=>errors.push(e.message));
await mkdir(new URL('../out/shots/',import.meta.url),{recursive:true});
for(let i=1;i<=17;i++){
  await page.goto('http://localhost:4174/#'+i);
  await page.evaluate(()=>document.fonts.ready);
  await page.waitForFunction(n=>document.querySelectorAll('.slide').length===1&&document.querySelector('.slide-'+n),i);
  await page.waitForTimeout(i===2?2800:1800);
  if([5,9,10].includes(i))await page.waitForFunction(()=>{
    let el=[...document.querySelectorAll('.demo span')].find(el=>el.textContent==='Step verified');
    if(!el)return false;
    while(el&&!el.classList.contains('demo')){if(Number(getComputedStyle(el).opacity)<.95)return false;el=el.parentElement;}
    return true;
  });
  const text=await page.locator('.slide-'+i).innerText();
  const visual={1:'.tutorial-wall .thumbnail',2:'.pain-windows .mini-app',3:'.mismatch .mini-app',4:'.brand-scene',5:'.steps-card',6:'.verified-card',7:'.waveform',8:'.source-cards',9:'.consent-card',10:'.demo',11:'.usage-chart',12:'.prices .illustration',13:'.market-orbit',14:'.gtm .illustration',15:'.flow-lines',16:'.brand-scene',17:'.limits .illustration'}[i];
  if(!await page.locator('.slide-'+i+' '+visual).first().isVisible())throw Error('Missing visual on slide '+i);
  if([5,6,7,8,9,10].includes(i)&&await page.locator('.demo>div:last-child').evaluate(el=>getComputedStyle(el).filter)!=='none')throw Error('Player color filter on slide '+i);
  if(i===13&&!text.includes('CIRCLES NOT TO SCALE'))throw Error('Market chart needs scale disclosure');
  if([2,10,15].includes(i)&&await page.locator('.slide-'+i+' h1').evaluate(el=>getComputedStyle(el).color)!=='rgb(255, 255, 255)')throw Error('Dark slide title contrast on '+i);
  if(/illustrative composition|illustrated example|composition fallback|Distribution roadmap|live billing status|Live inference still|broader context|Phonon requires setup/i.test(text))throw Error('Visible caveat on slide '+i);
  if(i===9&&!text.includes('Did it once? Rio does it for you next time.'))throw Error('Incorrect delegation title');
  if(i===11){
    if(!await page.locator('.console-mock').isVisible())throw Error('Missing console mock');
    if(!text.includes('Refund an order')||!text.includes('Create a promo code'))throw Error('Missing console results');
  }
  await page.screenshot({path:new URL('../out/shots/slide-'+String(i).padStart(2,'0')+'.png',import.meta.url).pathname});
}
await page.goto('http://localhost:4174/#5');
await page.keyboard.press('ArrowRight');
await page.waitForURL('**/#6');
await page.keyboard.press('Home');
await page.waitForURL('**/#1');
await page.keyboard.press('End');
await page.waitForURL('**/#17');
await page.locator('.slide-17').waitFor();
await page.waitForTimeout(100);
await page.keyboard.press('n');
if(!await page.locator('.notes').isVisible())throw Error('Missing notes');
await page.keyboard.press('n');
await page.locator('.notes').waitFor({state:'hidden'});
await page.mouse.click(100,500);
await page.waitForURL('**/#16');
await page.mouse.click(1800,500);
await page.waitForURL('**/#17');
await page.goto('http://localhost:4174/#garbage');
await page.locator('.slide-1').waitFor();
if(await page.locator('.slide-1 footer').innerText().then(t=>!t.includes('01 / 17')))throw Error('Invalid hash');
if(errors.length)throw Error(errors.join('\n'));
console.log('PASS: 17 screenshots at 1920×1080; keyboard, hash, notes, click navigation; zero page errors.');
await context.close();
await browser.close();
