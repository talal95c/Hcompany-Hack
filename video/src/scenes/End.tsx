import {Logo, Page, cue, ease, useShot} from '../ui/motion';

export function End() {
  const {f}=useShot('End');
  const button=cue('End','end.button');
  return <Page>
    <div style={{position:'absolute',top:349,width:'100%'}}><Logo frame={f} size={118}/></div>
    <div style={{position:'absolute',left:755,top:578,width:410,height:82,borderRadius:60,background:'#111',color:'#fff',display:'grid',placeItems:'center',fontSize:31,fontWeight:400,opacity:ease(f,button,button+14),transform:`translateY(${(1-ease(f,button,button+20))*20}px)`}}>Try Rio for free</div>
    <div style={{position:'absolute',top:692,width:'100%',textAlign:'center',fontSize:26,color:'#8a8a8a',opacity:ease(f,button,button+18)}}>rio.vignemale.com</div>
  </Page>;
}
