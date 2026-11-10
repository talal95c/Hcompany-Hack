import {Check, Cube, Cursor, GlowBox, Laptop, Page, TypeLine, bursts, cue, ease, gradient, pop, useShot} from '../ui/motion';

const tickEvents=['autopilot.tick.0','autopilot.tick.1','autopilot.tick.2'] as const;
export function Autopilot() {
  const {f,s}=useShot('Autopilot');
  const yes=cue('Autopilot','autopilot.yes'),blue=cue('Autopilot','autopilot.blue');
  const press=ease(f,yes,yes+4)-ease(f,yes+4,yes+14),hide=ease(f,yes+8,yes+24);
  return <Page>
    <div style={{position:'absolute',top:150,width:'100%',textAlign:'center',fontSize:72,letterSpacing:-3.2}}><TypeLine chunks={['Next time,','Rio does it','for you.']} starts={bursts('Autopilot',0,45,3)} frame={f} caret={false}/></div>
    <GlowBox style={{position:'absolute',left:470,top:320,width:980,height:116,opacity:1-hide}}>
      <div style={{position:'absolute',left:32,top:37,fontSize:31}}>Let Rio do this next time?</div>
      <div style={{position:'absolute',right:20,top:20,width:128,height:76,borderRadius:50,background:gradient,color:'#fff',display:'grid',placeItems:'center',fontSize:31,scale:1-press*.08}}>Yes</div>
    </GlowBox>
    <div style={{position:'absolute',left:450,top:337,width:1020,display:'flex',gap:36,justifyContent:'center',opacity:hide}}>{['Material','Base Color','Blue'].map((label,i)=>{const at=cue('Autopilot',tickEvents[i]);return <div key={label} style={{display:'flex',alignItems:'center',gap:13,fontSize:30}}><Check done={f>=at} frame={f} at={at}/>{label}</div>;})}</div>
    <Laptop frame={f} duration={s.duration} width={950} top={460}>
      <div style={{position:'absolute',inset:0,background:'#f4f4f5'}}>
        <div style={{height:32,background:'#e4e4e7',display:'flex',gap:22,padding:'7px 20px',fontSize:16,color:'#62626b'}}>Blender <span>Layout</span><span>Modeling</span><span>Shading</span></div>
        <div style={{position:'absolute',left:0,right:182,top:48,bottom:0,backgroundImage:'linear-gradient(#d4d4d859 1px,transparent 1px),linear-gradient(90deg,#d4d4d859 1px,transparent 1px)',backgroundSize:'32px 32px'}}/>
        <div style={{position:'absolute',right:0,top:48,bottom:0,width:170,background:'#e9e9ed',padding:'26px 16px',boxSizing:'border-box',fontSize:18,color:'#71717a'}}><div style={{marginBottom:30}}>Material</div><div style={{marginBottom:20}}>Base Color</div><div style={{height:24,borderRadius:5,background:f>=blue?'#3B82F6':'#aaa'}}/></div>
        <div style={{position:'absolute',width:420,height:378,left:155,top:62,scale:f>=blue?1+pop(f,blue)*.28:1,transform:`rotate(${f>=blue?(1-pop(f,blue))*-5:0}deg)`}}><Cube blue={f>=blue}/></div>
      </div>
    </Laptop>
    <Cursor frame={f} start={yes-43} click={yes} from={[1670,635]} to={[1365,377]}/>
  </Page>;
}
