import {Logo, Page, RioIcon, cue, ease, gradientText, pop, useShot} from '../ui/motion';

export function Introducing() {
  const {f}=useShot('Introducing');
  const drop=cue('Introducing','drop'),logo=cue('Introducing','introducing.logo');
  return <Page style={{background:f<drop?'#0b0b10':'#fff'}}>
    {f<drop?<div style={{position:'absolute',inset:0,display:'grid',placeItems:'center'}}><div style={{scale:.65+pop(f)*.35,filter:'drop-shadow(0 0 40px #FF8A6B26)'}}><RioIcon size={210}/></div></div>:f<logo?<div style={{position:'absolute',inset:0,display:'flex',alignItems:'center',justifyContent:'center',fontSize:88,fontWeight:400,letterSpacing:-4,transform:`translateY(${(1-ease(f,drop,drop+16))*20}px)`}}><span style={gradientText}>Introducing</span></div>:<div style={{position:'absolute',inset:0,display:'flex',alignItems:'center',justifyContent:'center'}}><Logo frame={f} at={logo} size={126}/></div>}
  </Page>;
}
