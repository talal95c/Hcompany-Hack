import React from "react";
import { AbsoluteFill, Easing, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { RioMark } from "./RioMark";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const LogoReveal: React.FC<{ ink: string; paper: string }> = ({ ink, paper }) => {
  const { width, height } = useVideoConfig();
  return (
    <AbsoluteFill style={{ backgroundColor: paper, alignItems: "center", justifyContent: "center" }}>
      <RioMark ink={ink} size={Math.min(width, height) * 0.3} />
    </AbsoluteFill>
  );
};

export const IconReveal: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const tile = width * 0.5;
  const t = interpolate(frame, [0, 0.9 * fps], [0, 1], {
    ...clamp,
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });
  return (
    <AbsoluteFill style={{ backgroundColor: "#ececec", alignItems: "center", justifyContent: "center" }}>
      <div
        style={{
          width: tile,
          height: tile,
          borderRadius: tile * 0.2245,
          backgroundColor: "#000",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          opacity: t,
          scale: interpolate(t, [0, 1], [0.86, 1], { output: "perceptual-scale" }),
        }}
      >
        <RioMark ink="#fff" size={tile * 0.5} delay={Math.round(0.35 * fps)} />
      </div>
    </AbsoluteFill>
  );
};
