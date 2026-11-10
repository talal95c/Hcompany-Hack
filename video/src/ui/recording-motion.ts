export type CursorPoint = {time:number;x:number;y:number};
export type RecordingLog = {width:number;height:number;fps:number;duration:number;samples:CursorPoint[];clicks:(CursorPoint&{label:string})[];blueTime?:number};
export type Anchor = {frame:number;time:number};
type Camera = {scale:number;x:number;y:number};
export type RecordingTimeline = {log:RecordingLog;anchors:Anchor[];duration:number;clicks:(CursorPoint&{label:string;frame:number})[];cameras:Camera[]};

const clamp = (n:number,lo=0,hi=1) => Math.max(lo,Math.min(hi,n));
const mix = (a:number,b:number,p:number) => a+(b-a)*p;

export function sourceAt(anchors:Anchor[],frame:number) {
  if(frame<=anchors[0].frame) return anchors[0].time;
  for(let i=1;i<anchors.length;i++) {
    if(frame<=anchors[i].frame) {
      const a=anchors[i-1],b=anchors[i];
      return mix(a.time,b.time,(frame-a.frame)/(b.frame-a.frame));
    }
  }
  return anchors[anchors.length-1].time;
}

export function frameAt(anchors:Anchor[],time:number) {
  for(let i=1;i<anchors.length;i++) {
    const a=anchors[i-1],b=anchors[i];
    if(time<=b.time&&b.time>a.time) return mix(a.frame,b.frame,clamp((time-a.time)/(b.time-a.time)));
  }
  return anchors[anchors.length-1].frame;
}

export function cursorAt(log:RecordingLog,time:number):CursorPoint {
  const samples=log.samples;
  if(!samples.length) return {time,x:log.width/2,y:log.height/2};
  let lo=0,hi=samples.length-1;
  while(lo<hi) {
    const mid=Math.floor((lo+hi)/2);
    if(samples[mid].time<time) lo=mid+1; else hi=mid;
  }
  const b=samples[lo],a=samples[Math.max(0,lo-1)];
  const p=b.time===a.time?0:clamp((time-a.time)/(b.time-a.time));
  return {time,x:mix(a.x,b.x,p),y:mix(a.y,b.y,p)};
}

export function createRecordingTimeline(log:RecordingLog,anchors:Anchor[],duration:number,zoomEnd:number):RecordingTimeline {
  if(![log.width,log.height,log.fps,log.duration,duration].every(n=>Number.isFinite(n)&&n>0)) throw new Error('Invalid recording dimensions or duration');
  if(anchors.length<2||anchors[0].frame!==0||anchors[anchors.length-1].frame!==duration) throw new Error('Recording anchors must cover the scene');
  anchors.forEach((a,i)=>{
    if(!Number.isFinite(a.frame)||!Number.isFinite(a.time)||a.time<0||a.time>=log.duration||(i>0&&(a.frame<=anchors[i-1].frame||a.time<anchors[i-1].time))) throw new Error('Recording anchors must increase within the clip');
  });
  for(const points of [log.samples,log.clicks]) points.forEach((p,i)=>{
    if(![p.time,p.x,p.y].every(Number.isFinite)||p.time<0||p.time>log.duration||p.x<0||p.x>log.width||p.y<0||p.y>log.height||(i>0&&p.time<points[i-1].time)) throw new Error('Invalid cursor log');
  });
  const clicks=log.clicks.map(c=>({...c,frame:frameAt(anchors,c.time)}));
  const cameras:Camera[]=[];
  const value={scale:1,x:.5,y:.5},velocity={scale:0,x:0,y:0};
  for(let step=0;step<=duration*2;step++) {
    const frame=step/2;
    const active=clicks.filter(c=>c.frame-14<=frame&&frame<=Math.min(c.frame+40,zoomEnd)).at(-1);
    const target=active?{scale:2,x:clamp((active.x/log.width-.08)/.84),y:clamp((active.y/log.height-.08)/.84)}:{scale:1,x:value.x,y:value.y};
    if(value.scale<1.0005&&active) {value.x=target.x;value.y=target.y;}
    for(const key of ['scale','x','y'] as const) {
      velocity[key]+=(190*(target[key]-value[key])-28*velocity[key])/120;
      value[key]+=velocity[key]/120;
    }
    const scale=Math.max(1,value.scale);
    cameras.push({scale,x:-clamp(value.x)*(scale-1),y:-clamp(value.y)*(scale-1)});
  }
  return {log,anchors,duration,clicks,cameras};
}

export function recordingAt(timeline:RecordingTimeline,frame:number) {
  const {cameras,log,anchors,clicks}=timeline;
  const index=clamp(frame*2,0,cameras.length-1),a=cameras[Math.floor(index)],b=cameras[Math.ceil(index)];
  const camera={scale:mix(a.scale,b.scale,index%1),x:mix(a.x,b.x,index%1),y:mix(a.y,b.y,index%1)};
  const time=sourceAt(anchors,frame),cursor=cursorAt(log,time);
  const lastClick=clicks.filter(c=>c.frame<=frame).at(-1);
  return {camera,cursor,time,lastClick};
}
