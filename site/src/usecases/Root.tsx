import { Composition } from 'remotion';
import '@fontsource-variable/inter';
import { Blender } from './Blender';
import { Spreadsheet } from './Spreadsheet';
import { Voice } from './Voice';
import { DURATION, FPS } from './primitives';

export function RemotionRoot() {
  return <>{[{ id: 'Blender', component: Blender }, { id: 'Spreadsheet', component: Spreadsheet }, { id: 'Voice', component: Voice }].map(c => <Composition key={c.id} {...c} width={640} height={400} fps={FPS} durationInFrames={DURATION} />)}</>;
}
