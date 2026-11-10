import {GlowBox, Page, RioIcon, TypeLine, Waveform, bursts, cue, ease, useShot} from '../ui/motion';

export function Voice() {
  const {f,s}=useShot('Ask');
  const answer=cue('Ask','ask.answer');
  return <Page>
    <div style={{position:'absolute',top:233,width:'100%',textAlign:'center',fontSize:76,letterSpacing:-3.5}}>Ask anything, by voice.</div>
    <GlowBox style={{position:'absolute',left:360,top:414,width:1200,height:310,transform:`translateY(${(1-ease(f,0,28))*30}px)`}}>
      <div style={{position:'absolute',top:18,left:22,right:35,display:'flex',alignItems:'center',justifyContent:'space-between'}}><RioIcon size={58}/><Waveform frame={f}/><span style={{fontSize:23,color:'#8a8a8a',width:120,textAlign:'right'}}>{f<answer?'Listening…':'Rio'}</span></div>
      <div style={{position:'absolute',left:48,top:98,fontSize:43,letterSpacing:-1.5}}><TypeLine chunks={['Why','Base Color?']} starts={bursts('Ask',0,43,2)} frame={f} caret={f<answer}/></div>
      <div style={{position:'absolute',left:48,top:189,fontSize:34,color:'#666',letterSpacing:-.8}}><TypeLine chunks={['It','sets','the','material’s','main','color.']} starts={bursts('Ask',answer,s.duration-61,6)} frame={f} caret={f>=answer}/></div>
    </GlowBox>
  </Page>;
}
