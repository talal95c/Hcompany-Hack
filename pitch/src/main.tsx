import React, {useEffect, useState, useRef} from 'react';
import {createRoot} from 'react-dom/client';
import {AnimatePresence, motion, useReducedMotion} from 'motion/react';
import {Player} from '@remotion/player';
import {Blender} from './usecases/Blender';
import {Spreadsheet} from './usecases/Spreadsheet';
import {Voice} from './usecases/Voice';
import {PLANS} from './plans';
import {notes} from './notes';
import '@fontsource-variable/inter';
import '@fontsource/geist-mono/400.css';
import '@fontsource/ibm-plex-mono/400.css';
import './style.css';
import './modern.css';
import './color.css';
import {TutorialWall, Mismatch, PainWindows, FeatureLife, TeamLife, Illustration, MarketVisual, FlowLines} from './visuals';
import mark from '../public/rio-mark-black.svg?inline';
import qr from '../public/qr.svg?inline';
import revealImage from '../public/readme-hero.webp?inline';
import closeImage from '../public/rio-hill.webp?inline';

const print = new URLSearchParams(location.search).has('print');
const asset=(s:string)=>s==='qr.svg'?qr:mark;
const EASE=[.22,1,.36,1] as const;
function HeroTitle({lines}:{lines:string[]}) {
 const reduced=useReducedMotion();
 let index=0;
 return <h1>{lines.map((line,i)=><React.Fragment key={line}>{i>0&&<br/>}{line.split(' ').map(word=><motion.span className="hero-word" key={index++} initial={print||reduced?false:{opacity:0,y:18,filter:'blur(5px)'}} animate={{opacity:1,y:0,filter:'blur(0px)'}} transition={{duration:.65,delay:print||reduced?0:index*.045,ease:EASE}}>{word}{' '}</motion.span>)}</React.Fragment>)}</h1>;
}
function BrandScene({close=false}:{close?:boolean}){
 const reduced=useReducedMotion();
 return <motion.img className="brand-scene" src={close?closeImage:revealImage} alt="" initial={false} animate={{scale:print||reduced?1:1.04}} transition={{duration:8,ease:'linear'}}/>;
}
function Cursor({x=1540,y=680}:{x?:number;y?:number}) {
 const reduced=useReducedMotion();
 return <motion.div className="cursor" style={{left:x,top:y}} initial={print||reduced?false:{x:-180,y:100,opacity:0}} animate={{x:[-180,-70,0],y:[100,-35,0],opacity:1}} transition={print||reduced?{duration:0}:{duration:1.25,ease:EASE,delay:.25}}>
 <motion.span className="cursor-ripple" initial={false} animate={print||reduced?{}:{scale:[.3,1.4],opacity:[0,.6,0]}} transition={{delay:1.4,duration:.6}}/>
 <svg width="65" height="78" viewBox="0 0 31 38"><path d="M3 3L27 22L16 25L10 34Z" fill="#FF6B35" stroke="white" strokeWidth="2"/></svg></motion.div>;
}
function Demo({kind='blender',large=false}:{kind?:string;large?:boolean}) {
 const reduced=useReducedMotion();
 if(kind==='teams')return <div className="console-mock">
   <div className="console-top"><img src={asset('rio-mark-black.svg')} alt=""/><span>ACME / TEAM WORKSPACE</span><span className="console-avatar">AC</span></div>
   <div className="console-body"><nav><b>Workspace</b><span className="selected">Tutorials</span><span>Knowledge</span><span>Members</span><span>Usage</span></nav>
   <div className="console-main"><div className="console-heading"><div><label>TEAM LIBRARY</label><h3>Know-how, shared.</h3></div><span className="console-add">+ Add tutorial</span></div>
   <div className="console-search">Search your team’s knowledge<span>⌘ K</span></div>
   <div className="console-result"><label>INTERNAL TOOLS / 5 STEPS</label><h3>Refund an order</h3><p>Comptoir · Orders → Order → Refund</p><span className="console-ready">Ready to follow →</span></div>
   <div className="console-result"><label>MARKETING / 4 STEPS</label><h3>Create a promo code</h3><p>Comptoir · Marketing → Discounts → New</p></div>
   <div className="console-bottom"><span>Shared with your team</span><span>2 tutorials</span></div></div></div></div>;
 const c=kind==='voice'?Voice:kind==='sheet'?Spreadsheet:Blender;
 const frames=kind==='blender'?360:270;
 return <div className={'demo '+(large?'large':'')}><div className="demo-label"><span className="window-dots"><i/><i/><i/></span><span>RIO / PRODUCT WALKTHROUGH</span><span>↗</span></div><Player component={c} durationInFrames={frames} fps={30} compositionWidth={640} compositionHeight={400} autoPlay={!print&&!reduced} loop muted controls={false} initialFrame={print||reduced?(kind==='blender'?330:218):(kind==='blender'?260:130)} style={{width:'100%'}}/></div>
}
const features=[
 {title:'Any YouTube tutorial becomes a live lesson.',sub:'Paste a link. Start doing.',kind:'blender',problem:'A linear video cannot see your app.',how:'Transcript + key frames → milestones linked to video timestamps.',power:['Gladia','Holo vision','Holo 4 27B']},
 {title:'Rio points to your next click. And sees when it’s done.',sub:'No “next” button. Your screen is the checkpoint.',kind:'sheet',problem:'Menus move. Coordinates break.',how:'Screenshot grounding + local change detection → on-screen verification.',power:['Holo 4 35B-A3B','Local screen watch']},
 {title:'Stuck? Just ask. By voice or text.',sub:'“Show me again.” “What is this menu?”',kind:'voice',problem:'One small question stops the whole lesson.',how:'Screen context → answer or guidance. Team knowledge → web if configured.',power:['Gladia Live','Holo','Linkup','Gradium Phonon']},
 {title:'No tutorial? Just say your goal.',sub:'“Make a budget chart in Calc.”',kind:'sheet',problem:'The right tutorial does not always exist.',how:'Research several sources → a lesson. Web-page text first; web agent if needed.',power:['H Agents deep-search-pro','web-surfer-pro','Linkup fallback']},
 {title:'Did it once? Rio does it for you next time.',sub:'Your consent. Stop anytime. Check the result.',kind:'blender',problem:'Learning the task should not mean repeating it forever.',how:'Reuse milestones → act → verify. Fast mode skips narration.',power:['Holo computer use','Devin · eligible runs → tested scripts']}
];
function Feature({i}:{i:number}) {const f=features[i];return <><div className="feature"><div><p className="eyebrow">0{i+1} / {['PASTE A LINK','FOLLOW THE CURSOR','ASK ANYTHING','START WITH A GOAL','DELEGATE'][i]}</p><h1>{f.title}</h1><p className="sub">{f.sub}</p></div><div className={'feature-stage feature-stage-'+i}><Demo kind={f.kind}/><FeatureLife i={i}/></div></div><div className="power-strip"><label>POWERED BY</label><div className="pills">{f.power.map(p=><span className={'brand-chip brand-'+p.split(' ')[0].toLowerCase()} key={p}>{p}</span>)}</div></div>{i===1&&<Cursor x={1490} y={570}/>}</>}
function Pain(){
 const reduced=useReducedMotion();
 const counter=useRef<HTMLSpanElement>(null);
 useEffect(()=>{
  if(print||reduced)return;
  let frame=0;const start=performance.now();
  const tick=(now:number)=>{const t=Math.min(1,(now-start)/2400);const seconds=Math.round(600+3000*(1-Math.pow(1-t,3)));if(counter.current)counter.current.textContent=Math.floor(seconds/60)+':'+String(seconds%60).padStart(2,'0');if(t<1)frame=requestAnimationFrame(tick)};
  frame=requestAnimationFrame(tick);return()=>cancelAnimationFrame(frame);
 },[reduced]);
 return <><p className="eyebrow">THE TUTORIAL TAX</p><h1>A 10-min tutorial takes an hour.<br/>A 1-hour tutorial takes the afternoon.</h1><PainWindows/><div className="timeline"><div className="video-time">10:00 <span>OF VIDEO</span></div><motion.div className="track" initial={print||reduced?false:{width:'16.67%'}} animate={{width:'100%'}} transition={{duration:2.4,ease:EASE}}/><div className="markers">{['Pause','Rewind','Alt-tab'].map((x,i)=><motion.span key={i} initial={print||reduced?false:{opacity:0,y:12,scale:.9}} animate={{opacity:1,y:0,scale:1}} transition={{delay:print||reduced?0:.4+i*.17,ease:EASE}}>{x}</motion.span>)}</div><p className="elapsed"><span className="time-digits" ref={counter}>60:00</span><span>OF YOUR TIME</span></p></div></>;
}
function Market(){return <><p className="eyebrow">A CATEGORY ALREADY VALIDATED</p><h1>Software is everywhere.<br/>Knowing how to use it isn’t.</h1><MarketVisual/><div className="market"><div><small>Gartner, 2024 Market Guide<br/>via WalkMe · walkme.com/content/2024-gartner-market-guide-for-digital-adoption-platforms/</small></div><div><small>SAP News Center · 12 Sep 2024<br/>news.sap.com/2024/09/sap-completes-walkme-acquisition/</small></div><div><small>Grand View Research · 2025 report<br/>grandviewresearch.com/industry-analysis/corporate-e-learning-market-report</small></div></div></>}
function Architecture(){return <><p className="eyebrow">ARCHITECTURE / BUILT AROUND H COMPANY</p><h1>Local guidance. Connected intelligence.</h1><div className="architecture"><div className="stack"><Illustration/><label>USER’S COMPUTER</label><h3>React + Tauri / Rust</h3><p>Tutor · cursor · autopilot</p><span className="node-chip">Phonon · local voice</span></div><div className="stack central"><Illustration kind={1}/><label>AI SERVICES ↔ DESKTOP + CLOUD</label><h2>H Company</h2><h3>Holo + H Agents</h3><p>Vision · grounding · research</p><div className="pills"><span className="brand-gladia">Gladia</span><span className="brand-linkup">Linkup</span><span className="brand-devin">Devin</span></div></div><div className="stack"><Illustration kind={3}/><label>RIO CLOUD ↔ DESKTOP</label><h3>Cloudflare Worker</h3><p>D1 · knowledge · team console</p><span className="node-chip">Stripe · billing</span></div></div><FlowLines/></>}
function Content({n}:{n:number}) {
 if(n>=4&&n<=8)return <Feature i={n-4}/>;
 switch(n){
 case 0:return <><TutorialWall/><div className="center cold"><HeroTitle lines={['Who here learned','a software from','a YouTube tutorial?']}/></div></>;
 case 1:return <Pain/>;
 case 2:return <><p className="eyebrow">WHY IT BREAKS</p><h1 className="huge">The video can’t see your screen.</h1><Mismatch/><p className="sub">The menu moved. Your version is different. You’re stuck.</p><Cursor x={1470} y={650}/></>;
 case 3:return <><BrandScene/><div className="reveal"><img src={mark}/><p className="eyebrow">YOUR IN-APP LEARNING COMPANION</p><HeroTitle lines={['That’s over. Meet Rio.']}/><p className="sub">Paste a tutorial. Rio walks you through it inside your own app.</p></div><Cursor x={1350} y={280}/></>;
 case 9:return <><div className="demo-title"><p className="eyebrow">DEMO / BLENDER</p><h1>Live: a donut in 5 steps in Blender.</h1></div><Demo large/></>;
 case 10:return <><div className="feature teams"><div><p className="eyebrow">WHO PAYS</p><h1>Every new hire replays the same tutorials.</h1><p className="sub">From individual learning to team onboarding.</p><TeamLife/></div><Demo kind="teams"/></div></>;
 case 11:return <><p className="eyebrow">PRICING / USD</p><h1>Start free. Grow with your team.</h1><div className="prices">{PLANS.map((p,i)=><div key={p.id} className={p.dark?'dark':''}><Illustration kind={i}/><label>{p.name}</label><strong>{p.monthly===null?'Custom':'$'+p.monthly}<small>{p.monthly? p.seats?'/seat/mo':'/mo':''}</small></strong><p>{p.annual? '$'+p.annual+(p.seats?'/seat/mo':'/mo')+' billed annually':p.tagline}</p><p>{p.f[0]}<br/>{p.f[1]}</p></div>)}</div><p className="footnote">Payments by <b className="stripe-word">Stripe</b> · Research once. Reuse across the team.</p></>;
 case 12:return <Market/>;
 case 13:return <><p className="eyebrow">GO-TO-MARKET / THE PLAN</p><h1>Win the learner.<br/>Become the team’s memory.</h1><div className="gtm">{[['01','Public tutorial library','SEO: “how to X in Y”'],['02','Team console','Shared lessons + internal knowledge'],['03','Enterprise','Internal tools + SSO']].map(([a,b,c],i)=><div key={a}><Illustration kind={[0,2,3][i]}/><label>{a} →</label><h2>{b}</h2><p>{c}</p></div>)}</div><FlowLines/></>;
 case 14:return <Architecture/>;
 case 15:return <><BrandScene close/><div className="closing"><img className="mark" src={mark}/><HeroTitle lines={['Stop watching tutorials.','Do them.']}/><p className="sub">Built at the H Company hackathon.</p></div><div className="qr"><img src={qr} alt="QR code to rio.vignemale.com"/><p>rio.vignemale.com</p></div><Cursor x={1480} y={295}/></>;
 default:return <><p className="eyebrow">APPENDIX / HONEST LIMITS & HOW WE TEST</p><h1>Trust is earned on the actual screen.</h1><div className="limits"><div><Illustration/><label>TEST</label><h3>A learner simulator</h3><p>Replays real runs. Checks the app state.</p></div><div><Illustration kind={2}/><label>CONTROL</label><h3>You stay in charge</h3><p>Consent first. Stop anytime. Verify results.</p></div><div><Illustration kind={1}/><label>LIMITS</label><h3>Not universal reliability</h3><p>Pointing & vague requests. No Wayland.</p></div></div></>;
 }}
function Slide({n}:{n:number}){const reduced=useReducedMotion();return <section className={'slide slide-'+(n+1)+([1,9,14].includes(n)?' dark-slide':'')+(reduced?' reduced':'')}><div className="progress" style={{width:((n+1)/17*100)+'%'}}/><div className="slide-content"><Content n={n}/></div><footer><span>{n===0?'':'RIO / LEARN BY DOING'}</span><span>{String(n+1).padStart(2,'0')} / 17</span></footer></section>}
function readHash(){const v=Number(location.hash.slice(1));return Number.isFinite(v)?Math.max(0,Math.min(16,v-1)):0}
function App(){const [n,setN]=useState(readHash);const [show,setShow]=useState(false);const [scale,setScale]=useState(Math.min(innerWidth/1920,innerHeight/1080));
 const reduced=useReducedMotion();
 const go=(x:number)=>{location.hash=String(Math.max(0,Math.min(16,x))+1)};
 useEffect(()=>{const resize=()=>setScale(Math.min(innerWidth/1920,innerHeight/1080));const hash=()=>setN(readHash());const key=(e:KeyboardEvent)=>{if(['ArrowRight',' ','PageDown','ArrowLeft','PageUp','Home','End','n','N','f','F'].includes(e.key))e.preventDefault();if(['ArrowRight',' ','PageDown'].includes(e.key))go(n+1);if(['ArrowLeft','PageUp'].includes(e.key))go(n-1);if(e.key==='Home')go(0);if(e.key==='End')go(16);if(e.key.toLowerCase()==='n')setShow(s=>!s);if(e.key.toLowerCase()==='f'){if(document.fullscreenElement)void document.exitFullscreen();else void document.documentElement.requestFullscreen().catch(()=>{});}};addEventListener('resize',resize);addEventListener('hashchange',hash);addEventListener('keydown',key);return()=>{removeEventListener('resize',resize);removeEventListener('hashchange',hash);removeEventListener('keydown',key)}},[n]);
 if(print)return <main className="print">{Array.from({length:17},(_,i)=><Slide key={i} n={i}/>)}</main>;
 return <><main className="viewport" onClick={e=>go(n+(e.clientX<innerWidth/2?-1:1))}><div className="stage" style={{transform:`translate(-50%,-50%) scale(${scale})`}}><AnimatePresence initial={false}><motion.div className="slide-transition" key={n} initial={reduced?false:{opacity:0,y:12,filter:'blur(5px)'}} animate={{opacity:1,y:0,filter:'blur(0px)'}} exit={{opacity:0,y:-8,filter:reduced?'blur(0px)':'blur(4px)'}} transition={{duration:reduced?0:.5,ease:EASE}}><Slide n={n}/></motion.div></AnimatePresence></div></main>{show&&<aside className="notes" onClick={e=>e.stopPropagation()}><label>NOTES / {n+1} · N TO CLOSE</label><p>{notes[n]}</p></aside>}</>
}
createRoot(document.getElementById('root')!).render(<App/>);
