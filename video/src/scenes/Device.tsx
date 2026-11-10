import {Img, staticFile} from 'remotion';
import {Laptop, Page, TypeLine, bursts, cue, ease, useShot} from '../ui/motion';

export function Device() {
  const {f,s}=useShot('Device');
  const change=cue('Device','device.photo'),p=ease(f,change,change+18);
  return <Page>
    <div style={{position:'absolute',top:113,width:'100%',textAlign:'center',fontSize:76,letterSpacing:-3.5}}>Rio shows you where.</div>
    <div style={{position:'absolute',top:218,width:'100%',textAlign:'center',fontSize:48,letterSpacing:-1.8,color:'#8a8a8a'}}><TypeLine chunks={['Right','on your','screen.']} starts={bursts('Device',0,66,3)} frame={f} caret={false}/></div>
    <Laptop frame={f} duration={s.duration} width={1130} top={335}>
      <Img src={staticFile('photos/blender-material-tab.jpg')} style={{position:'absolute',width:'100%',height:'100%',objectFit:'contain',transform:`translateX(${-p*15}%)`,opacity:1-p,filter:`blur(${p*(1-p)*12}px)`}}/>
      <Img src={staticFile('photos/blender-base-color.jpg')} style={{position:'absolute',width:'100%',height:'100%',objectFit:'contain',transform:`translateX(${(1-p)*15}%)`,opacity:p,filter:`blur(${p*(1-p)*12}px)`}}/>
    </Laptop>
  </Page>;
}
