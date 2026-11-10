import {Check, Page, cue, ease, gradientText, useShot} from '../ui/motion';

const labels=['Watching the tutorial','Splitting it into steps','Finding the buttons on your screen','Ready'];
const events=['check.tick.0','check.tick.1','check.tick.2','check.tick.3'] as const;
export function Checklist() {
  const {f}=useShot('Checklist');
  return <Page>
    <div style={{position:'absolute',top:245,left:410,width:1100,padding:'24px 0',borderRadius:16,background:'#f7f7f7',textAlign:'center',fontSize:27,color:'#555'}}>youtube.com/watch?v=make-it-blue <span style={{color:'#999'}}>· in Blender</span></div>
    <div style={{position:'absolute',left:530,top:385,width:930}}>
      <div style={{fontSize:62,letterSpacing:-2.8,marginBottom:42,...gradientText}}>Generating…</div>
      {labels.map((label,i)=>{
        const at=cue('Checklist',events[i]),done=f>=at,active=i===0||f>=cue('Checklist',events[i-1]);
        return <div key={label} style={{display:'flex',alignItems:'center',gap:23,height:82,fontSize:34,color:active?'#111':'#bbb',transform:`translateY(${(1-ease(f,0,24))*14}px)`}}><Check done={done} frame={f} at={at}/><span>{label}</span></div>;
      })}
    </div>
  </Page>;
}
