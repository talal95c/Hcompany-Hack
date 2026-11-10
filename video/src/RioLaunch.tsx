import {AbsoluteFill, Audio, Sequence, interpolate, staticFile} from 'remotion';
import beats from './beats.json';
import {Hook} from './scenes/Hook';
import {Dock} from './scenes/Dock';
import {Introducing} from './scenes/Introducing';
import {Prompt} from './scenes/Prompt';
import {Checklist} from './scenes/Checklist';
import {Device} from './scenes/Device';
import {Voice} from './scenes/Voice';
import {Autopilot} from './scenes/Autopilot';
import {Orbit} from './scenes/Orbit';
import {Claim} from './scenes/Claim';
import {End} from './scenes/End';
import {shot} from './ui/motion';

const components=[Hook,Dock,Introducing,Prompt,Checklist,Device,Voice,Autopilot,Orbit,Claim,End];
const clicks=[beats.events['prompt.send'],beats.events['autopilot.yes'],beats.events['check.tick.0'],beats.events['check.tick.1'],beats.events['check.tick.2'],beats.events['check.tick.3']];
export function RioLaunch() {
  const duration=beats.segment.durationInFrames;
  return <AbsoluteFill style={{background:'white'}}>
    {beats.scenes.map((s,i)=>{const Scene=components[i];return <Sequence key={s.name} name={s.name} from={s.from} durationInFrames={s.duration}><Scene/></Sequence>;})}
    <Audio src={staticFile('audio/loser.mp3')} startFrom={Math.round(beats.segment.startSeconds*60)} volume={f=>.5*interpolate(f,[0,32,duration-95,duration-30,duration-1],[0,1,1,0,0],{extrapolateLeft:'clamp',extrapolateRight:'clamp'})}/>
    {clicks.map((from,i)=><Sequence key={`click-${i}`} from={from} durationInFrames={18}><Audio src={staticFile('audio/sfx-275.mp3')} volume={.1}/></Sequence>)}
    {['Hook','Prompt','Ask','Claim'].map(name=><Sequence key={`typing-${name}`} from={shot(name).from} durationInFrames={105}><Audio src={staticFile('audio/sfx-1386.mp3')} volume={.035}/></Sequence>)}
    {[beats.events['introducing.logo'],beats.events['device.photo'],shot('Orbit').from].map(from=><Sequence key={`whoosh-${from}`} from={from} durationInFrames={26}><Audio src={staticFile('audio/sfx-1492.mp3')} volume={.055}/></Sequence>)}
  </AbsoluteFill>;
}
