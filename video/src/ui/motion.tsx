import type {CSSProperties, ReactNode} from 'react';
import {loadFont} from '@remotion/google-fonts/Inter';
import {AbsoluteFill, Easing, Img, interpolate, spring, staticFile, useCurrentFrame} from 'remotion';
import beats from '../beats.json';

export const {fontFamily} = loadFont('normal', {weights: ['400', '500', '600'], subsets: ['latin']});
export const ink = '#111111';
export const grey = '#8a8a8a';
export const orange = '#e98548';
export const gradient = 'linear-gradient(115deg, #FF6B35, #FF8A6B 48%, #F45D9A)';
export const gradientText: CSSProperties = {background:gradient, backgroundClip:'text', WebkitBackgroundClip:'text', color:'transparent'};
export const ease = (f:number, from:number, to:number) => interpolate(f,[from,to],[0,1],{extrapolateLeft:'clamp',extrapolateRight:'clamp',easing:Easing.bezier(.22,1,.36,1)});
export const pop = (f:number, at=0) => spring({frame:Math.max(0,f-at),fps:60,config:{damping:18,stiffness:160,mass:.8}});
export const shot = (name:string) => {
  const found = beats.scenes.find(s=>s.name===name);
  if (!found) throw new Error(`Unknown scene: ${name}`);
  return found;
};
export function cue(name:string, event:keyof typeof beats.events) {
  const value = beats.events[event];
  if (typeof value !== 'number') throw new Error(`Not a scalar cue: ${event}`);
  return value-shot(name).from;
}
export function bursts(name:string, start:number, end:number, count:number) {
  const s=shot(name);
  const lattice=[...beats.beats,...beats.onsets].map(b=>b.frame-s.from).filter(f=>f>=start&&f<=end);
  if (!lattice.length) throw new Error(`No audio events inside ${name} ${start}–${end}`);
  return Array.from({length:count},(_,i)=>{
    const target=start+(end-start)*i/Math.max(1,count-1);
    return lattice.reduce((a,b)=>Math.abs(a-target)<=Math.abs(b-target)?a:b);
  });
}
export function Page({children,style}: {children:ReactNode;style?:CSSProperties}) {
  return <AbsoluteFill style={{background:'#fff',color:ink,fontFamily,overflow:'hidden',...style}}>{children}</AbsoluteFill>;
}
export function TypeLine({chunks,starts,frame,join=' ',caret=true,rate=1.2}: {chunks:string[];starts:number[];frame:number;join?:string;caret?:boolean;rate?:number}) {
  let text='';
  chunks.forEach((chunk,i)=>{
    if(frame>=starts[i]) text+=(i?join:'')+chunk.slice(0,Math.floor((frame-starts[i]+1)/rate));
  });
  return <span style={{whiteSpace:'pre'}}>{text}{caret&&<span style={{display:'inline-block',width:3,height:'.94em',background:'currentColor',marginLeft:6,verticalAlign:'-.08em',opacity:Math.floor(frame/22)%2===0?1:0}}/>}</span>;
}
export function Brackets({children}: {children:ReactNode}) {
  return <div style={{position:'relative',display:'inline-block',padding:'44px 58px'}}>{children}{[0,1,2,3].map(i=><span key={i} style={{position:'absolute',width:15,height:15,borderColor:'#999',borderStyle:'solid',borderWidth:0,...(i<2?{top:0,borderTopWidth:2}:{bottom:0,borderBottomWidth:2}),...(i%2?{right:0,borderRightWidth:2}:{left:0,borderLeftWidth:2})}}/>)}</div>;
}
export function AppIcon({name,size=100,style}: {name:string;size?:number;style?:CSSProperties}) {
  return <Img src={staticFile(`apps/${name}.png`)} style={{width:size,height:size,objectFit:'contain',...style}}/>;
}
export function RioIcon({size=120,style}: {size?:number;style?:CSSProperties}) {
  return <Img src={staticFile('brand/rio-app-icon.svg')} style={{width:size,height:size,...style}}/>;
}
export function Logo({frame=100,at=0,size=110}: {frame?:number;at?:number;size?:number}) {
  const p=pop(frame,at);
  return <div style={{display:'flex',alignItems:'center',justifyContent:'center',gap:12}}>
    <RioIcon size={size*1.28} style={{transform:`translateX(${(1-p)*180}px) rotate(${(1-p)*-140}deg) scale(${.7+p*.3})`}}/>
    <div style={{fontSize:size*.94,fontWeight:500,letterSpacing:-size*.055,clipPath:`inset(0 ${100-ease(frame,at+12,at+40)*100}% 0 0)`}}>Rio</div>
  </div>;
}
export function Cursor({frame,start,click,from,to,size=55}: {frame:number;start:number;click:number;from:[number,number];to:[number,number];size?:number}) {
  const t=ease(frame,start,click),r=ease(frame,click,click+26);
  return <div style={{position:'absolute',left:from[0]+(to[0]-from[0])*t,top:from[1]+(to[1]-from[1])*t,opacity:ease(frame,start,start+6)*(1-ease(frame,click+30,click+42)),zIndex:30}}>
    <div style={{position:'absolute',width:90,height:90,border:`2px solid ${orange}`,borderRadius:100,left:-45,top:-45,opacity:frame>=click?1-r:0,scale:.2+r*1.5}}/>
    <svg width={size} height={size*1.22} viewBox="0 0 31 38" style={{filter:'drop-shadow(0 4px 5px #0002)',scale:frame>=click&&frame<click+7?.9:1}}><path d="M3 3Q2 1 5 3L27 22Q29 25 25 25L16 25L11 33Q9 36 8 32Z" fill={orange} stroke="white" strokeWidth="2" strokeLinejoin="round"/></svg>
  </div>;
}
export function GlowBox({children,style}: {children:ReactNode;style?:CSSProperties}) {
  return <div style={{padding:2,borderRadius:30,background:'linear-gradient(120deg,#e7e7e7,#FF8A6B99,#F45D9A77)',boxShadow:'0 12px 45px #F45D9A0c, 0 3px 12px #11111105',...style}}><div style={{height:'100%',boxSizing:'border-box',borderRadius:28,background:'white',position:'relative'}}>{children}</div></div>;
}
export function Check({done,frame,at,size=34}: {done:boolean;frame:number;at:number;size?:number}) {
  return <div style={{width:size,height:size,flexShrink:0,position:'relative',scale:done?.8+pop(frame,at)*.2:1}}>{done?<svg viewBox="0 0 32 32" width={size} height={size}><circle cx="16" cy="16" r="14" stroke="#10B981" strokeWidth="1.5" fill="#ecfdf5"/><path d="m9 16 5 5 9-10" fill="none" stroke="#10B981" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>:<div style={{width:size-5,height:size-5,border:'2px solid #e8e8e8',borderTopColor:'#FF8A6B',borderRightColor:'#3B82F6',borderRadius:100,rotate:`${frame*5}deg`}}/>}</div>;
}
export function Laptop({children,frame,duration=300,width=1120,top=335}: {children:ReactNode;frame:number;duration?:number;width?:number;top?:number}) {
  const p=Math.min(1,frame/duration),enter=ease(frame,0,38);
  return <div style={{position:'absolute',top,left:'50%',width,height:width*.635,perspective:2200,transform:`translateX(-50%) scale(${.91+enter*.09+p*.035})`}}>
    <div style={{position:'absolute',width:'100%',height:'100%',transformStyle:'preserve-3d',transform:`translateY(${(1-enter)*110}px) rotateX(${9-p*5}deg) rotateY(${-17+p*27}deg) rotateZ(${-3+p*4}deg)`}}>
      <div style={{position:'absolute',inset:'0 0 38px',background:'#141416',border:'3px solid #77777a',borderRadius:26,padding:'22px 14px 15px',boxShadow:'10px 30px 60px #0002',boxSizing:'border-box'}}>
        <div style={{position:'absolute',width:7,height:7,borderRadius:8,background:'#35353b',left:'50%',top:8}}/>
        <div style={{position:'relative',width:'100%',height:'100%',background:'#252525',overflow:'hidden',borderRadius:8}}>{children}</div>
      </div>
      <div style={{position:'absolute',bottom:24,left:'-8%',width:'116%',height:24,background:'linear-gradient(#e4e4e7,#929298)',borderRadius:'3px 3px 70px 70px',boxShadow:'0 20px 22px #00000018',transform:'rotateX(18deg)'}}><div style={{position:'absolute',top:0,left:'43%',width:'14%',height:7,background:'#88888e',borderRadius:'0 0 8px 8px'}}/></div>
      <div style={{position:'absolute',height:8,bottom:20,left:'-3%',width:'106%',background:'#bcbcc2',borderRadius:'0 0 100% 100%'}}/>
    </div>
  </div>;
}
export function Cube({blue=false}: {blue?:boolean}) {
  return <svg viewBox="0 0 500 450" style={{width:'100%',height:'100%',filter:'drop-shadow(0 22px 18px #0002)'}}><path d="M250 45 425 140 250 240 75 140Z" fill={blue?'#78a4ff':'#ddd'}/><path d="M75 140 250 240 250 430 75 330Z" fill={blue?'#3B82F6':'#a1a1a8'}/><path d="M250 240 425 140 425 330 250 430Z" fill={blue?'#1d4ed8':'#71717a'}/></svg>;
}
export function Waveform({frame}: {frame:number}) {
  return <div style={{display:'flex',alignItems:'center',height:54,gap:5}}>{Array.from({length:36},(_,i)=><span key={i} style={{width:5,borderRadius:6,height:7+Math.pow(Math.sin(frame*.13+i*.83),2)*36*Math.sin((i+1)/37*Math.PI),background:i%3===0?'#F45D9A':'#FF8A6B'}}/>)}</div>;
}
export function useShot(name:string) {return {f:useCurrentFrame(),s:shot(name)};}
