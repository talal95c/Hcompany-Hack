import {AppIcon, Cursor, GlowBox, Page, RioIcon, TypeLine, bursts, cue, ease, gradient, useShot} from '../ui/motion';

function GridRoom({frame,out}: {frame:number;out:number}) {
  const grid={backgroundImage:'linear-gradient(#ffffff99 1px,transparent 1px),linear-gradient(90deg,#ffffff99 1px,transparent 1px)',backgroundSize:'64px 64px'};
  return <div style={{position:'absolute',left:250,top:55,width:1420,height:1000,overflow:'hidden',borderRadius:'50%',opacity:1-ease(frame,out,out+50),scale:.7+ease(frame,0,42)*.3,background:'linear-gradient(125deg,#FFE3D3,#f5c6dc 56%,#f7efff)',perspective:900}}>
    <div style={{position:'absolute',inset:'-30% -10% 20%',...grid,transform:'translateZ(-140px)'}}/>
    <div style={{position:'absolute',width:'150%',height:'100%',left:'-25%',top:'45%',...grid,backgroundColor:'#ffc9b9',transformOrigin:'top',transform:'rotateX(70deg)'}}/>
    <div style={{position:'absolute',width:'55%',height:'150%',left:'-35%',top:'-25%',...grid,backgroundColor:'#f9cee5',transform:'rotateY(62deg)'}}/>
  </div>;
}
export function Prompt() {
  const {f}=useShot('Prompt');
  const send=cue('Prompt','prompt.send'),out=cue('Prompt','prompt.roomOut');
  const enter=ease(f,0,34),press=ease(f,send,send+5)-ease(f,send+5,send+17);
  return <Page>
    <GridRoom frame={f} out={out}/>
    <div style={{position:'absolute',top:205,left:0,width:'100%',textAlign:'center'}}><RioIcon size={86}/></div>
    <div style={{position:'absolute',top:325,width:'100%',textAlign:'center',fontSize:76,letterSpacing:-3.5}}>Paste a tutorial</div>
    <div style={{position:'absolute',left:340,top:480,width:1240,height:242,transform:`perspective(1200px) rotateX(${(1-enter)*25}deg) scale(${.86+enter*.14+ease(f,send+18,send+42)*.06})`}}>
      <GlowBox style={{width:'100%',height:'100%'}}>
        <div style={{position:'absolute',left:36,top:38,fontSize:38,letterSpacing:-1.2}}><TypeLine frame={f} chunks={['youtube.','com/','watch?','v=','make-it-blue']} starts={bursts('Prompt',42,153,5)} join=""/></div>
        <div style={{position:'absolute',left:36,top:159,height:42,display:'flex',gap:12,alignItems:'center',opacity:ease(f,174,190),color:'#666',fontSize:27}}><span>·</span><AppIcon name="blender" size={32}/><span>in Blender</span></div>
        <div style={{position:'absolute',right:28,bottom:24,width:70,height:70,borderRadius:20,background:gradient,color:'white',display:'grid',placeItems:'center',fontSize:42,scale:1-.07*press}}>↑</div>
      </GlowBox>
    </div>
    <Cursor frame={f} start={send-43} click={send} from={[1770,870]} to={[1535,665]}/>
  </Page>;
}
