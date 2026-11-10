import {Img, staticFile} from 'remotion';
import beats from '../beats.json';
import {AppIcon, Page, TypeLine, cue, ease, useShot} from '../ui/motion';

const apps=['finder','notes','google-chrome','blender','davinci-resolve','visual-studio-code','safari'];
export function Dock() {
  const {f,s}=useShot('Dock');
  const switches=beats.events['dock.switches'].map(t=>t-s.from);
  const current=Math.max(0,switches.filter(t=>f>=t).length-1);
  const active=current%2===0?2:3;
  const previous=current%2===0?3:2;
  const p=ease(f,switches[current],switches[current]+8);
  return <Page>
    <Img src={staticFile('brand/rio-hill.jpg')} style={{width:'100%',height:'100%',objectFit:'cover',filter:'blur(12px)',scale:1.08+f*.00012}}/>
    <div style={{position:'absolute',inset:0,background:'linear-gradient(#ffffffa6,#ffffff1a 65%,#ffffff66)'}}/>
    <div style={{position:'absolute',top:275,width:'100%',textAlign:'center',fontSize:78,letterSpacing:-3.5}}><TypeLine frame={f} chunks={['Pause.','Rewind.','Lost.']} starts={[cue('Dock','dock.words.0'),cue('Dock','dock.words.1'),cue('Dock','dock.words.2')]}/></div>
    <div style={{position:'absolute',left:385,top:505,width:1150,height:196,borderRadius:40,background:'#ffffff45',border:'1px solid #ffffffaa',boxShadow:'0 18px 70px #00000012',backdropFilter:'blur(22px)',transform:`translateY(${(1-ease(f,0,25))*50}px)`}}>
      {apps.map((app,i)=>{
        const distance=Math.abs(i-active),focus=distance===0?1:distance===1?.9:.8;
        return <div key={app} style={{position:'absolute',left:35+i*154,top:20,width:150,height:142,transform:`translateY(${i===active?-10*p:0}px) scale(${focus})`,filter:`blur(${distance>1?(distance-1)*1.6:0}px)`,opacity:distance>2?.68:1}}><AppIcon name={app} size={140}/></div>;
      })}
      <div style={{position:'absolute',left:35+(previous+(active-previous)*p)*154+8,top:173,width:124,height:4,borderRadius:5,background:'#fff',boxShadow:'0 2px 12px #ffffff99'}}/>
    </div>
  </Page>;
}
