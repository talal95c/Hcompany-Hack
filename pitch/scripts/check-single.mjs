import {chromium} from 'playwright';
import {stat} from 'node:fs/promises';
const browser=await chromium.connectOverCDP('http://localhost:29229');
const context=await browser.newContext({viewport:{width:1920,height:1080},deviceScaleFactor:1,reducedMotion:'reduce'});
const page=await context.newPage();
const errors=[];
page.on('pageerror',e=>errors.push(e.message));
page.on('requestfailed',r=>errors.push(r.url()));
const file=new URL('../out/rio-pitch.html',import.meta.url);
for(const n of [1,4,6,10,15,16]){
 await page.goto(file.href+'#'+n);
 await page.evaluate(()=>document.fonts.ready);
 await page.waitForTimeout(400);
 const loaded=await page.evaluate(()=>[...document.images].every(i=>i.complete&&i.naturalWidth>0)&&document.fonts.check('16px "Inter Variable"')&&document.fonts.check('16px "Geist Mono"'));
 if(!loaded)throw Error('Missing images/fonts on file slide '+n);
 if([6,10].includes(n)&&!await page.locator('.demo').isVisible())throw Error('Missing player');
 await page.screenshot({path:new URL('../out/shots/file-slide-'+String(n).padStart(2,'0')+'.png',import.meta.url).pathname});
}
await page.goto(file.href+'?print');
await page.evaluate(()=>document.fonts.ready);
if(await page.locator('.slide').count()!==17)throw Error('Print missing slides');
if(await page.locator('.time-digits').innerText()!=='60:00')throw Error('Print counter not final');
if(errors.length)throw Error(errors.join('\n'));
console.log('PASS: file:// slides 1, 4, 6, 10, 15, 16; all images/fonts loaded; zero page/request errors; reduced motion and 17-slide final print state.');
console.log('Single HTML bytes:',(await stat(file)).size);
await context.close();
await browser.close();
