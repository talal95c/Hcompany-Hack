import {Img, staticFile} from 'remotion';
import {Page, TypeLine, bursts, pop, useShot} from '../ui/motion';

const assets=['apps/blender.png','photos/blender-material-tab.jpg','apps/google-chrome.png','apps/davinci-resolve.png','brand/rio-hill.jpg','apps/visual-studio-code.png','photos/desktop-app-guide.jpg','apps/finder.png','apps/notes.png','photos/blender-base-color.jpg','apps/safari.png','brand/readme-hero.jpg','apps/terminal.png','apps/calendar.png','photos/blender-ask.jpg','apps/preview.png','apps/mail.png','apps/docker-desktop.png','photos/blender-material-tab.jpg','apps/system-settings.png'];
export function Orbit() {
  const {f}=useShot('Orbit');
  const starts=bursts('Orbit',0,44,assets.length);
  return <Page>
    <div style={{position:'absolute',inset:0,perspective:1500}}>
      <div style={{position:'absolute',left:960,top:540,transformStyle:'preserve-3d',transform:'rotateX(14deg) rotateZ(-9deg)'}}>{assets.map((asset,i)=>{
        const angle=i/assets.length*Math.PI*2+f*.0027;
        const depth=Math.sin(angle),p=pop(f,starts[i]);
        const photo=!asset.startsWith('apps/');
        return <div key={`${asset}-${i}`} style={{position:'absolute',width:photo?198:125,height:photo?132:125,left:-80,top:-60,background:photo?'#fff':'#ffffffaa',borderRadius:photo?14:25,overflow:'hidden',boxShadow:'0 7px 20px #0000000d',transform:`translate3d(${Math.cos(angle)*674}px,${Math.sin(angle)*378}px,${depth*110}px) rotateY(${Math.cos(angle)*-16}deg) rotateZ(9deg) scale(${p})`}}><Img src={staticFile(asset)} style={{width:'100%',height:'100%',objectFit:photo?'cover':'contain'}}/></div>;
      })}</div>
    </div>
    <div style={{position:'absolute',top:493,width:'100%',textAlign:'center',fontSize:70,letterSpacing:-3.2}}><TypeLine chunks={['Every app','you use.']} starts={bursts('Orbit',0,43,2)} frame={f} caret={false}/></div>
  </Page>;
}
