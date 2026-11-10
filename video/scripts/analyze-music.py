"""Analyze the locally supplied recording; emit only timing metadata, never audio."""
import json
from pathlib import Path

import librosa
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FPS = 60
y, sr = librosa.load(ROOT / 'public/audio/loser.mp3', sr=22050)
onset = librosa.onset.onset_strength(y=y, sr=sr)
tracker_tempo, beat_indices = librosa.beat.beat_track(onset_envelope=onset, sr=sr)
beats = librosa.frames_to_time(beat_indices, sr=sr)
onset_indices = librosa.onset.onset_detect(onset_envelope=onset, sr=sr)
onsets = librosa.frames_to_time(onset_indices, sr=sr)
steady = beats[(beats > 12) & (beats < 80)]
bpm = float(60 / np.polyfit(np.arange(len(steady)), steady, 1)[0])

def nearest(t):
    return float(beats[np.argmin(np.abs(beats-t))])

start, end = nearest(2.043), nearest(43.259)
frame = lambda t: round((float(t)-start)*FPS)
duration = frame(end)
scene_plan = [('Hook',2.043),('Dock',5.317),('Introducing',9.985),('Prompt',13.607),('Checklist',18.692),('Device',21.571),('Ask',26.633),('Autopilot',30.952),('Orbit',34.575),('Claim',37.454),('End',40.356)]
scenes = [{'name':n,'from':frame(nearest(t)),'sourceSeconds':nearest(t)} for n,t in scene_plan]
for i,s in enumerate(scenes):
    s['duration'] = (scenes[i+1]['from'] if i+1<len(scenes) else duration)-s['from']

events = {}
def cue(name, seconds):
    events[name] = frame(nearest(seconds))

for name,t in [('drop',10.704),('introducing.logo',11.819),('prompt.roomOut',14.698),('prompt.send',17.949),('device.photo',24.102),('ask.answer',28.073),('autopilot.yes',32.392),('autopilot.blue',33.483),('end.button',41.076)]:
    cue(name,t)
for prefix, times in {
    'hook.words':[2.043,2.415,3.460,3.808],
    'dock.words':[5.666,6.780,8.197],
    'check.tick':[19.017,19.760,20.480,21.200],
    'autopilot.tick':[32.763,33.135,33.483],
    'claim.tags':[37.454,37.825,38.197,38.545],
}.items():
    for i,t in enumerate(times): cue(f'{prefix}.{i}',t)

selected_beats = [{'seconds':round(float(t-start),6),'sourceSeconds':round(float(t),6),'frame':frame(t)} for t in beats if start<=t<end]
selected_onsets = [{'seconds':round(float(t-start),6),'sourceSeconds':round(float(t),6),'frame':frame(t),'strength':round(float(onset[i]),4)} for t,i in zip(onsets,onset_indices) if start<=t<end]
events['dock.switches'] = sorted(set([frame(nearest(t)) for t in [5.317,6.037,6.780,7.477]] + [o['frame'] for o in selected_onsets if 7.825<o['sourceSeconds']<10.2]))
data = {'fps':FPS,'segment':{'startSeconds':start,'endSeconds':end,'durationInFrames':duration},'tempo':{'trackerBpm':float(np.ravel(tracker_tempo)[0]),'fittedBpm':round(bpm,4),'halfTimeBpm':round(bpm/2,4),'method':'librosa onset envelope + beat tracking; linear fit of steady beats 12–80s resolves quantized lag tempo'},'dropSourceSeconds':nearest(10.704),'downbeats':{'method':'Candidate four-beat phase anchored at the verified energy entrance at 10.704s; not a learned downbeat classifier','frames':[b['frame'] for j,b in enumerate(selected_beats) if (j-next(i for i,v in enumerate(selected_beats) if v['frame']==events['drop']))%4==0]},'beats':selected_beats,'onsets':selected_onsets,'scenes':scenes,'events':events}
(ROOT/'src/beats.json').write_text(json.dumps(data,indent=2)+'\n')
print(f'Segment: {start:.6f}–{end:.6f}s; {duration} frames; fitted {bpm:.4f} BPM / {bpm/2:.4f} half-time')
for s in scenes:
    print(f"{s['name']:14} frame={s['from']:4} duration={s['duration']:3} nearest beat delta=0 frames")
