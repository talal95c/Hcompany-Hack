import { Composition } from "remotion";
import { GetRio, DURATION, FPS, H, W } from "./GetRio";

export const Root = () => (
  <Composition id="GetRio" component={GetRio} durationInFrames={DURATION} fps={FPS} width={W} height={H} />
);
