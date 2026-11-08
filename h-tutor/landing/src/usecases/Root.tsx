import { Composition } from 'remotion';
import '@fontsource-variable/inter';
import { Blender, BLENDER_DURATION } from './Blender';
import { Spreadsheet } from './Spreadsheet';
import { Voice } from './Voice';
import { DURATION, FPS } from './primitives';
import { TeamsSearch, TEAMS_SEARCH_DURATION } from './TeamsSearch';
import '@fontsource-variable/inter/opsz.css';
import '@fontsource/geist-mono/300.css';
import '@fontsource/geist-mono/400.css';
import '../styles.css';

export function RemotionRoot() {
  return <>{[{ id: 'Blender', component: Blender, durationInFrames: BLENDER_DURATION }, { id: 'Spreadsheet', component: Spreadsheet, durationInFrames: DURATION }, { id: 'Voice', component: Voice, durationInFrames: DURATION }].map(c => <Composition key={c.id} {...c} width={640} height={400} fps={FPS} />)}<Composition id="TeamsSearch" component={TeamsSearch} durationInFrames={TEAMS_SEARCH_DURATION} width={548} height={366} fps={FPS} /></>;
}
