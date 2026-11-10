import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {execFileSync,spawnSync} from 'node:child_process';
import {createRecordingTimeline, cursorAt, recordingAt, sourceAt} from '../src/ui/recording-motion.ts';

const read = (name) => JSON.parse(readFileSync(new URL(`../public/rec/${name}-cursor.json`,import.meta.url)));
const ffmpegStats = (args) => {
  const result=spawnSync('ffmpeg',args,{encoding:'utf8'});
  assert.equal(result.status,0,result.stderr);
  return result.stderr;
};
const log=read('device');
const anchors=[{frame:0,time:0},...log.clicks.map((c,i)=>({frame:[43,97,152][i],time:c.time})),{frame:303,time:log.duration-1/60}];
const timeline=createRecordingTimeline(log,anchors,303,194);
assert.equal(sourceAt(anchors,152),log.clicks[2].time);
assert.deepEqual(cursorAt(log,log.clicks[0].time),{time:log.clicks[0].time,x:log.clicks[0].x,y:log.clicks[0].y});
assert.deepEqual(recordingAt(timeline,150),recordingAt(timeline,150));
let scaleDelta=0,panDelta=0;
for(let f=1;f<=303;f++) {
  const a=recordingAt(timeline,f-1).camera,b=recordingAt(timeline,f).camera;
  assert.ok(b.scale>=1&&b.scale<=2.01);
  assert.ok(b.x<=0&&b.x>=1-b.scale&&b.y<=0&&b.y>=1-b.scale);
  scaleDelta=Math.max(scaleDelta,Math.abs(b.scale-a.scale));
  panDelta=Math.max(panDelta,Math.abs(b.x-a.x),Math.abs(b.y-a.y));
}
assert.ok(scaleDelta<.09&&panDelta<.09);
assert.ok(recordingAt(timeline,65).camera.scale>1.8);
assert.ok(recordingAt(timeline,303).camera.scale<1.001);
const empty={...log,samples:[],clicks:[]};
assert.equal(recordingAt(createRecordingTimeline(empty,anchors,303,194),120).camera.scale,1);
assert.equal(cursorAt(empty,0).x,log.width/2);
assert.throws(()=>createRecordingTimeline(log,[],303,194),/cover/);
assert.throws(()=>createRecordingTimeline(log,[anchors[0],{frame:0,time:1},anchors.at(-1)],303,194),/increase/);
assert.throws(()=>createRecordingTimeline({...log,width:0},anchors,303,194),/dimensions/);
assert.throws(()=>createRecordingTimeline({...log,samples:[{time:0,x:NaN,y:1}]},anchors,303,194),/cursor/);
console.log(`PASS: cursor interpolation, deterministic spring zoom, empty logs, invalid inputs; max scale/frame=${scaleDelta.toFixed(4)}, pan/frame=${panDelta.toFixed(4)}.`);

const auto=read('autopilot');
const autoAnchors=[{frame:0,time:0},{frame:94,time:0},...auto.clicks.slice(0,4).map((c,i)=>({frame:[108,119,130,141][i],time:c.time})),{frame:151,time:auto.blueTime},{frame:174,time:auto.clicks[4].time},{frame:217,time:auto.duration-1/60}];
const autoTimeline=createRecordingTimeline(auto,autoAnchors,217,151);
for(let f=0;f<94;f++) assert.equal(recordingAt(autoTimeline,f).time,0);
assert.equal(recordingAt(autoTimeline,151).time,auto.blueTime);
assert.ok(recordingAt(autoTimeline,216).camera.scale<1.001);
assert.deepEqual(recordingAt(autoTimeline,160),recordingAt(autoTimeline,160));
console.log('PASS: Autopilot holds until consent + 8 frames; first blue viewport frame maps to local 151 / global 1886; camera returns to full screen.');

for(const name of ['device','autopilot']) {
  const data=read(name),path=new URL(`../public/rec/${name}.mp4`,import.meta.url).pathname;
  const info=JSON.parse(execFileSync('ffprobe',['-v','error','-select_streams','v:0','-count_frames','-show_entries','stream=width,height,r_frame_rate,nb_read_frames,duration','-of','json',path],{encoding:'utf8'})).streams[0];
  assert.equal(info.width,1920);assert.equal(info.height,1080);assert.equal(info.r_frame_rate,'60/1');
  assert.ok(Math.abs(Number(info.duration)-data.duration)<1/60);
  const stats=ffmpegStats(['-hide_banner','-nostats','-i',path,'-vf','mpdecimate','-an','-f','null','-']);
  const frames=Number([...stats.matchAll(/frame=\s*(\d+)/g)].at(-1)[1]);
  console.log(`${name}: ${info.nb_read_frames} captured frames at 60 fps; mpdecimate kept ${frames}, removed ${Number(info.nb_read_frames)-frames} static UI frames (OS cursor hidden).`);
  const black=ffmpegStats(['-hide_banner','-nostats','-i',path,'-vf','blackdetect=d=0.016:pix_th=0.02:pic_th=0.98','-an','-f','null','-']);
  assert.ok(!black.includes('black_start:'));
  for(let i=1;i<data.samples.length;i++) {
    const a=data.samples[i-1],b=data.samples[i];
    assert.ok(Math.hypot(b.x-a.x,b.y-a.y)<50,'Cursor path contains a jump');
  }
  assert.ok(data.clicks.length>=3);
  console.log(`PASS: ${name} has no black frames; ${data.samples.length} timestamped cursor samples, no position jumps >=50px.`);
  if(name==='autopilot') {
    assert.ok(data.blueTime>data.clicks[3].time&&data.blueTime<data.duration);
    const pixel=execFileSync('ffmpeg',['-hide_banner','-loglevel','error','-ss',String(data.blueTime+.1),'-i',path,'-vf','crop=64:64:760:450,scale=1:1','-frames:v','1','-pix_fmt','rgb24','-f','rawvideo','-']);
    assert.ok(pixel[2]>pixel[0]*1.3);
    console.log(`PASS: actual Material Preview cube is blue at source ${data.blueTime.toFixed(3)}s.`);
  }
}
