import React from "react";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { DEFAULT_PALETTE, Palette, serifStack } from "./theme";

export type LowerThirdProps = {
  heading: string; // name / label
  subheading: string | null; // role / detail
  palette: Palette;
  durationInFrames: number;
};

export const lowerThirdDefaults: LowerThirdProps = {
  heading: "Jalāl al-Dīn Rumi",
  subheading: "13th-century Sufi poet",
  palette: DEFAULT_PALETTE,
  durationInFrames: 150,
};

export const LowerThird: React.FC<LowerThirdProps> = ({
  heading,
  subheading,
  palette,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const enter = spring({ frame, fps, config: { damping: 200 } });
  const slideX = interpolate(enter, [0, 1], [-60, 0]);
  const barScale = interpolate(enter, [0, 1], [0, 1]);
  const textOpacity = interpolate(enter, [0, 1], [0, 1]);

  const subOpacity = interpolate(frame, [10, 26], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const exit = interpolate(
    frame,
    [durationInFrames - 12, durationInFrames],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const glowScale = 1 + 0.05 * Math.sin((frame / fps) * 0.8);

  return (
    <AbsoluteFill
      style={{
        background: `linear-gradient(180deg, ${palette.bg1} 0%, ${palette.bg2} 100%)`,
        opacity: exit,
      }}
    >
      <AbsoluteFill
        style={{
          background: `radial-gradient(circle at 22% 78%, ${palette.glow} 0%, rgba(0,0,0,0) 55%)`,
          transform: `scale(${glowScale})`,
        }}
      />
      <div
        style={{
          position: "absolute",
          left: 150,
          bottom: 170,
          display: "flex",
          alignItems: "center",
          gap: 34,
          transform: `translateX(${slideX}px)`,
          opacity: textOpacity,
        }}
      >
        <div
          style={{
            width: 8,
            height: 132,
            borderRadius: 4,
            background: palette.accent,
            transform: `scaleY(${barScale})`,
            transformOrigin: "center",
          }}
        />
        <div>
          <div
            style={{
              fontFamily: serifStack,
              fontSize: 82,
              fontWeight: 500,
              lineHeight: 1.05,
              color: palette.fg,
              textShadow: "0 4px 30px rgba(10,6,18,0.55)",
            }}
          >
            {heading}
          </div>
          {subheading ? (
            <div
              style={{
                fontFamily: serifStack,
                fontStyle: "italic",
                fontSize: 40,
                fontWeight: 400,
                color: palette.accent,
                marginTop: 14,
                letterSpacing: 1.5,
                opacity: subOpacity,
              }}
            >
              {subheading}
            </div>
          ) : null}
        </div>
      </div>
    </AbsoluteFill>
  );
};
