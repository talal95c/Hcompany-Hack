import {Brackets, Page, TypeLine, cue, useShot} from '../ui/motion';

const events=['hook.words.0','hook.words.1','hook.words.2','hook.words.3'] as const;
export function Hook() {
  const {f}=useShot('Hook');
  return <Page><div style={{position:'absolute',inset:0,display:'flex',alignItems:'center',justifyContent:'center'}}>
    <Brackets><div style={{fontSize:80,fontWeight:400,letterSpacing:-3.8}}><TypeLine frame={f} chunks={['One','tutorial.','Twelve','Alt+Tabs.']} starts={events.map(event=>cue('Hook',event))}/></div></Brackets>
  </div></Page>;
}
