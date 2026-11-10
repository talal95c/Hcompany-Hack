import {Composition} from 'remotion';
import {RioLaunch} from './RioLaunch';
import beats from './beats.json';
export const Root = () => <Composition id="RioLaunch" component={RioLaunch} width={1920} height={1080} fps={60} durationInFrames={beats.segment.durationInFrames}/>;
