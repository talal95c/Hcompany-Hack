import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const data=JSON.parse(readFileSync(new URL('../src/beats.json',import.meta.url),'utf8'));
const lattice=new Set([...data.beats,...data.onsets].map(b=>b.frame));
function validateScenes(scenes,duration) {
  assert(scenes.length>0,'Empty timeline');
  assert.equal(scenes[0].from,0);
  for(const [i,s] of scenes.entries()) {
    assert(s.duration>0,'Empty scene');
    if(i) assert.equal(scenes[i-1].from+scenes[i-1].duration,s.from,'Gap or overlap');
  }
  assert.equal(scenes.at(-1).from+scenes.at(-1).duration,duration);
}
validateScenes(data.scenes,data.segment.durationInFrames);
assert.throws(()=>validateScenes([],data.segment.durationInFrames));
assert.throws(()=>validateScenes([{from:0,duration:0}],0));
assert.throws(()=>validateScenes([{from:0,duration:5},{from:6,duration:5}],11));
assert.equal(data.scenes[0].from,0);
assert.equal(data.scenes.at(-1).from+data.scenes.at(-1).duration,data.segment.durationInFrames);
for(const [i,s] of data.scenes.entries()) {
  assert(s.duration>0);
  if(i) assert.equal(data.scenes[i-1].from+data.scenes[i-1].duration,s.from);
  const nearest=data.beats.reduce((a,b)=>Math.abs(a.frame-s.from)<Math.abs(b.frame-s.from)?a:b);
  assert.equal(nearest.frame,s.from);
  console.log(`${s.name.padEnd(14)} start=${String(s.from).padStart(4)} nearest beat=${String(nearest.frame).padStart(4)} delta=0 frames`);
}
for(const [name,value] of Object.entries(data.events)) {
  for(const f of Array.isArray(value)?value:[value]) assert(lattice.has(f),`${name} at ${f} is not an onset or beat`);
}
assert(lattice.size>0);
assert(data.events.drop>data.scenes[2].from);
assert(data.events['autopilot.yes']<data.events['autopilot.blue']);
assert(Math.abs(data.tempo.fittedBpm-166)<1);
for(const name of ['drop','introducing.logo']) {
  const f=data.events[name];
  const b=data.beats.reduce((a,b)=>Math.abs(a.frame-f)<Math.abs(b.frame-f)?a:b);
  console.log(`${name.padEnd(14)} cut=${String(f).padStart(4)} nearest beat=${String(b.frame).padStart(4)} delta=${f-b.frame} frames`);
}
console.log(`PASS: 11 contiguous scenes; ${Object.keys(data.events).length} cue groups on beat/onset lattice; consent precedes execution.`);
console.log('PASS: empty timeline, empty scene and noncontiguous timeline are rejected.');
