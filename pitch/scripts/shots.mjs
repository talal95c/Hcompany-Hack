import {chromium} from 'playwright';
import {mkdir} from 'node:fs/promises';
const browser=await chromium.connectOverCDP('http://localhost:29229');
const context=await browser.newContext({viewport:{width:1920,height:1080},deviceScaleFactor:1});
const page=await context.newPage();
const errors=[];
page.on('pageerror', e=>errors.push(e.message));
await mkdir(new URL('../out/shots/',import.meta.url),{recursive:true});
for(let i=1;i<=17;i++){
  await page.goto('http://localhost:4174/#'+i);
  await page.evaluate(()=>document.fonts.ready);
  await page.waitForTimeout(1600);
  const text=await page.locator('.slide').innerText();
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
if(await page.locator('footer').innerText().then(t=>!t.includes('01 / 17')))throw Error('Invalid hash');
if(errors.length)throw Error(errors.join('\n'));
console.log('PASS: 17 screenshots at 1920×1080; keyboard, hash, notes, click navigation; zero page errors.');
await context.close();
await browser.close();
