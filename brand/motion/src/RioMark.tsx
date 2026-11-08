import React from "react";
import { Easing, interpolate, useCurrentFrame, useVideoConfig } from "remotion";

const BODY = "M24 0H84V40L64 60V20H24V60L0 84V24Z";
const LEG = "M24 60H64L96 84H48Z";

const outExpo = Easing.bezier(0.16, 1, 0.3, 1);
const inOut = Easing.bezier(0.65, 0, 0.35, 1);

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

type Props = {
  ink: string;
  size: number;
  delay?: number;
};

export const RioMark: React.FC<Props> = ({ ink, size, delay = 0 }) => {
  const frame = useCurrentFrame() - delay;
  const { fps } = useVideoConfig();
  const s = (sec: number) => sec * fps;

  const draw = interpolate(frame, [s(0.2), s(1.1)], [1, 0], { ...clamp, easing: inOut });
  const outline = interpolate(frame, [s(0.2), s(0.35), s(1.35), s(1.8)], [0, 1, 1, 0], clamp);
  const wipe = interpolate(frame, [s(0.9), s(1.5)], [-12, 184], { ...clamp, easing: inOut });
  const leg = interpolate(frame, [s(1.3), s(2.1)], [1, 0], { ...clamp, easing: outExpo });
  const legOpacity = interpolate(frame, [s(1.3), s(1.6)], [0, 1], clamp);

  return (
    <svg
      viewBox="-2 -2 100 88"
      width={size}
      height={(size * 88) / 100}
      style={{
        overflow: "visible",
        scale: interpolate(frame, [0, s(2.4)], [0.94, 1], {
          ...clamp,
          easing: outExpo,
          output: "perceptual-scale",
        }),
      }}
    >
      <defs>
        <clipPath id={`wipe-${delay}`}>
          <polygon points={`-300,-300 ${wipe + 300},-300 -300,${wipe + 300}`} />
        </clipPath>
      </defs>
      <path
        d={BODY}
        fill="none"
        stroke={ink}
        strokeWidth={1.25}
        strokeLinejoin="miter"
        vectorEffect="non-scaling-stroke"
        pathLength={1}
        strokeDasharray={1}
        strokeDashoffset={draw}
        opacity={outline}
      />
      <path d={BODY} fill={ink} clipPath={`url(#wipe-${delay})`} />
      <path
        d={LEG}
        fill={ink}
        opacity={legOpacity}
        style={{ translate: `${leg * 24}px ${leg * 18}px` }}
      />
    </svg>
  );
};
