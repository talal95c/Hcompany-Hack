import { Composition } from "remotion";
import { IconReveal, LogoReveal } from "./Logo";

const fps = 60;
const duration = 4 * fps;

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition id="LogoDark" component={LogoReveal} defaultProps={{ ink: "#fff", paper: "#000" }} durationInFrames={duration} fps={fps} width={1920} height={1080} />
      <Composition id="LogoLight" component={LogoReveal} defaultProps={{ ink: "#000", paper: "#fff" }} durationInFrames={duration} fps={fps} width={1920} height={1080} />
      <Composition id="LogoSquare" component={LogoReveal} defaultProps={{ ink: "#fff", paper: "#000" }} durationInFrames={duration} fps={fps} width={1080} height={1080} />
      <Composition id="AppIcon" component={IconReveal} durationInFrames={duration} fps={fps} width={1080} height={1080} />
    </>
  );
};
