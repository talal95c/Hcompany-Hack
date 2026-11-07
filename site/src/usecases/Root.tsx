import { Composition } from 'remotion';
import '@fontsource-variable/inter';
import { Blender, BLENDER_DURATION } from './Blender';
import { Spreadsheet } from './Spreadsheet';
import { Voice } from './Voice';
import { DURATION, FPS } from './primitives';

export function RemotionRoot() {
  return <>{[{ id: 'Blender', component: Blender, durationInFrames: BLENDER_DURATION }, { id: 'Spreadsheet', component: Spreadsheet, durationInFrames: DURATION }, { id: 'Voice', component: Voice, durationInFrames: DURATION }].map(c => <Composition key={c.id} {...c} width={640} height={400} fps={FPS} />)}</>;
}
