import {BlenderRecording} from '../ui/BlenderRecording';
import {Laptop, Page, TypeLine, bursts, useShot} from '../ui/motion';

export function Device() {
  const {f,s}=useShot('Device');
  return <Page>
    <div style={{position:'absolute',top:113,width:'100%',textAlign:'center',fontSize:76,letterSpacing:-3.5}}>Rio shows you where.</div>
    <div style={{position:'absolute',top:218,width:'100%',textAlign:'center',fontSize:48,letterSpacing:-1.8,color:'#8a8a8a'}}><TypeLine chunks={['Right','on your','screen.']} starts={bursts('Device',0,66,3)} frame={f} caret={false}/></div>
    <Laptop frame={f} duration={s.duration} width={1130} top={335}>
      <BlenderRecording name="device" frame={f}/>
    </Laptop>
  </Page>;
}
