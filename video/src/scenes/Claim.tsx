import {Page, TypeLine, bursts, cue, pop, useShot} from '../ui/motion';

const tags=[{text:'Voice',color:'#FF6B35',x:485,y:224,rotate:-5},{text:'Autopilot',color:'#111',x:1290,y:316,rotate:5},{text:'Any app',color:'#3B82F6',x:418,y:747,rotate:-5},{text:'Your consent',color:'#10B981',x:1120,y:816,rotate:4}];
const events=['claim.tags.0','claim.tags.1','claim.tags.2','claim.tags.3'] as const;
export function Claim() {
  const {f}=useShot('Claim');
  return <Page>
    <div style={{position:'absolute',top:429,width:'100%',textAlign:'center',fontSize:86,letterSpacing:-4.5}}>Learn any software.</div>
    <div style={{position:'absolute',top:543,width:'100%',textAlign:'center',fontSize:66,letterSpacing:-3.2,color:'#8a8a8a'}}><TypeLine chunks={['By doing it,','not','watching it.']} starts={bursts('Claim',0,86,3)} frame={f}/></div>
    {tags.map((tag,i)=><div key={tag.text} style={{position:'absolute',left:tag.x,top:tag.y+Math.sin(f*.036+i)*5,background:tag.color,color:'#fff',fontSize:24,fontWeight:500,padding:'9px 15px',borderRadius:9,boxShadow:`0 5px 18px ${tag.color}22`,transform:`rotate(${tag.rotate}deg) scale(${pop(f,cue('Claim',events[i]))})`}}>{tag.text}<svg width="24" height="28" viewBox="0 0 24 28" style={{position:'absolute',right:i%2?undefined:-17,left:i%2?-17:undefined,top:i<2?34:-20,rotate:i%2?'180deg':undefined}}><path d="m3 2 17 14-9 1-2 8Z" fill={tag.color} stroke="#fff" strokeWidth="1.5"/></svg></div>)}
  </Page>;
}
