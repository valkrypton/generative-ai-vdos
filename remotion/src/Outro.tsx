import React from "react";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { DEFAULT_PALETTE, Palette, serifStack } from "./theme";

export type OutroProps = {
  heading: string; // e.g. "Thanks for watching"
  subheading: string | null; // e.g. "Subscribe for more"
  palette: Palette;
  durationInFrames: number;
};

export const outroDefaults: OutroProps = {
  heading: "Thanks for watching",
  subheading: "Subscribe for more",
  palette: DEFAULT_PALETTE,
  durationInFrames: 150,
};

export const Outro: React.FC<OutroProps> = ({
  heading,
  subheading,
  palette,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const enter = spring({ frame, fps, config: { damping: 200 } });
  const headingY = interpolate(enter, [0, 1], [34, 0]);
  const headingOpacity = interpolate(enter, [0, 1], [0, 1]);

  // Accent underline draws in from the center.
  const ruleScale = interpolate(frame, [8, 30], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const subOpacity = interpolate(frame, [20, 40], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const exit = interpolate(
    frame,
    [durationInFrames - 14, durationInFrames],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const glowScale = 1 + 0.06 * Math.sin((frame / fps) * 0.9);

  return (
    <AbsoluteFill
      style={{
        background: `linear-gradient(180deg, ${palette.bg1} 0%, ${palette.bg2} 100%)`,
        opacity: exit,
      }}
    >
      <AbsoluteFill
        style={{
          background: `radial-gradient(circle at 50% 50%, ${palette.glow} 0%, rgba(0,0,0,0) 55%)`,
          transform: `scale(${glowScale})`,
        }}
      />
      <AbsoluteFill
        style={{
          justifyContent: "center",
          alignItems: "center",
          flexDirection: "column",
          padding: "0 160px",
          textAlign: "center",
        }}
      >
        <div
          style={{
            fontFamily: serifStack,
            fontSize: 96,
            fontWeight: 500,
            lineHeight: 1.1,
            color: palette.fg,
            transform: `translateY(${headingY}px)`,
            opacity: headingOpacity,
            textShadow: "0 6px 40px rgba(10,6,18,0.55)",
          }}
        >
          {heading}
        </div>
        <div
          style={{
            width: 220,
            height: 4,
            borderRadius: 2,
            background: palette.accent,
            marginTop: 40,
            transform: `scaleX(${ruleScale})`,
          }}
        />
        {subheading ? (
          <div
            style={{
              fontFamily: serifStack,
              fontStyle: "italic",
              fontSize: 44,
              fontWeight: 400,
              color: palette.accent,
              marginTop: 40,
              letterSpacing: 2,
              opacity: subOpacity,
            }}
          >
            {subheading}
          </div>
        ) : null}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
