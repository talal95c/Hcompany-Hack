import {Freeze, OffthreadVideo, Sequence, staticFile} from 'remotion';
import deviceLog from '../../public/rec/device-cursor.json';
import autopilotLog from '../../public/rec/autopilot-cursor.json';
import {Check, Cursor, RioIcon, bursts, cue, ease, shot} from './motion';
import {createRecordingTimeline, recordingAt, type Anchor, type RecordingTimeline} from './recording-motion';

const device=shot('Device'),autopilot=shot('Autopilot');
const deviceClicks=bursts('Device',43,cue('Device','device.photo'),3);
const deviceAnchors:Anchor[]=[{frame:0,time:0},...deviceLog.clicks.map((c,i)=>({frame:deviceClicks[i],time:c.time})),{frame:device.duration,time:deviceLog.duration-1/60}];
const blue=cue('Autopilot','autopilot.blue');
const material=cue('Autopilot','autopilot.tick.0'),baseColor=cue('Autopilot','autopilot.tick.1');
const autoClicks=[material,Math.round((material+baseColor)/2),baseColor,Math.round((baseColor+blue)/2)];
const apply=bursts('Autopilot',blue+1,autopilot.duration-20,1)[0];
if(autopilotLog.blueTime===undefined) throw new Error('Autopilot recording needs a measured blueTime');
const autoAnchors:Anchor[]=[
  {frame:0,time:0},{frame:cue('Autopilot','autopilot.yes')+8,time:0},
  ...autopilotLog.clicks.slice(0,4).map((c,i)=>({frame:autoClicks[i],time:c.time})),
  {frame:blue,time:autopilotLog.blueTime},{frame:apply,time:autopilotLog.clicks[4].time},
  {frame:autopilot.duration,time:autopilotLog.duration-1/60},
];
const timelines={
  device:createRecordingTimeline(deviceLog,deviceAnchors,device.duration,deviceClicks[2]+42),
  autopilot:createRecordingTimeline(autopilotLog,autoAnchors,autopilot.duration,blue),
};

function RecordedVideo({name,timeline}: {name:string;timeline:RecordingTimeline}) {
  const {anchors}=timeline;
  return <>{anchors.slice(0,-1).map((a,i)=>{
    const b=anchors[i+1],rate=(b.time-a.time)*60/(b.frame-a.frame);
    return <Sequence key={i} from={a.frame} durationInFrames={b.frame-a.frame} layout="none">
      {rate===0?<Freeze frame={0}><OffthreadVideo src={staticFile(`rec/${name}.mp4`)} muted style={{width:'100%',height:'100%'}}/></Freeze>:
        <OffthreadVideo src={staticFile(`rec/${name}.mp4`)} muted trimBefore={Math.round(a.time*60)} playbackRate={rate} style={{width:'100%',height:'100%'}}/>}
    </Sequence>;
  })}</>;
}

export function BlenderRecording({name,frame}: {name:'device'|'autopilot';frame:number}) {
  const timeline=timelines[name],{camera,cursor,lastClick}=recordingAt(timeline,frame);
  const previous=recordingAt(timeline,Math.max(0,frame-1)).camera;
  const blur=Math.min(1.1,Math.abs(camera.scale-previous.scale)*15+Math.abs(camera.x-previous.x)*5);
  const progress=timeline.clicks.filter(c=>c.frame<=frame).length;
  const ready=name==='autopilot'&&frame>=blue;
  const label=ready?'Done — your cube is blue':name==='autopilot'?'Rio is taking the steps for you':progress<1?'Open Material Properties':progress<2?'Create a new material':'Choose Base Color';
  const visible=name==='device'?1:ease(frame,cue('Autopilot','autopilot.yes')+8,cue('Autopilot','autopilot.yes')+16);
  return <div style={{position:'absolute',inset:0,display:'grid',placeItems:'center',background:'#292929'}}>
    <div style={{position:'relative',width:'100%',aspectRatio:'16 / 9',overflow:'hidden'}}>
      <div style={{position:'absolute',inset:0,transformOrigin:'0 0',transform:`translate(${camera.x*100}%,${camera.y*100}%) scale(${camera.scale})`,filter:`blur(${blur}px)`}}>
        <RecordedVideo name={name} timeline={timeline}/>
      </div>
      <div style={{position:'absolute',left:`${(cursor.x/timeline.log.width*camera.scale+camera.x)*100}%`,top:`${(cursor.y/timeline.log.height*camera.scale+camera.y)*100}%`,transform:'scale(.65)',transformOrigin:'0 0',opacity:visible}}>
        <Cursor frame={lastClick?Math.min(30,frame-lastClick.frame):-1} start={-100} click={0} from={[0,0]} to={[0,0]} size={46}/>
      </div>
      <div style={{position:'absolute',left:'50%',top:14,transform:'translateX(-50%)',display:'flex',alignItems:'center',gap:12,padding:'10px 14px',borderRadius:22,background:'#15151dee',boxShadow:'0 4px 18px #0003',color:'white',fontSize:20,whiteSpace:'nowrap',opacity:visible}}>
        <RioIcon size={30}/><span>{label}</span>
        <span style={{background:'#ffffff19',padding:'5px 10px',borderRadius:12,fontSize:17}}>{Math.min(3,progress+1)} / 3</span>
        {(name==='device'?progress>=3:ready)&&<Check done frame={frame} at={name==='device'?timeline.clicks[2].frame:blue} size={25}/>}
      </div>
    </div>
  </div>;
}
