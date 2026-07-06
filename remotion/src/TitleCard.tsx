import React from "react";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { DEFAULT_PALETTE, Palette, serifStack } from "./theme";

export type TitleCardProps = {
  heading: string;
  subheading: string | null;
  palette: Palette;
  durationInFrames: number;
};

export const titleCardDefaults: TitleCardProps = {
  heading: "Your Title Here",
  subheading: "a short supporting line",
  palette: DEFAULT_PALETTE,
  durationInFrames: 150,
};

export const TitleCard: React.FC<TitleCardProps> = ({
  heading,
  subheading,
  palette,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  // Entrance: fade + lift, spring-eased.
  const enter = spring({ frame, fps, config: { damping: 200 } });
  const headingY = interpolate(enter, [0, 1], [40, 0]);
  const headingOpacity = interpolate(enter, [0, 1], [0, 1]);

  const subOpacity = interpolate(frame, [12, 30], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Gentle exit fade in the last 12 frames.
  const exit = interpolate(
    frame,
    [durationInFrames - 12, durationInFrames],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  // Soft breathing glow.
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
          justifyContent: "center",
          alignItems: "center",
          background: `radial-gradient(circle at 50% 62%, ${palette.glow} 0%, rgba(0,0,0,0) 55%)`,
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
            fontSize: 104,
            lineHeight: 1.15,
            fontWeight: 500,
            color: palette.fg,
            letterSpacing: 0.5,
            transform: `translateY(${headingY}px)`,
            opacity: headingOpacity,
            textShadow: "0 6px 40px rgba(10,6,18,0.55)",
          }}
        >
          {heading}
        </div>
        {subheading ? (
          <div
            style={{
              fontFamily: serifStack,
              fontSize: 44,
              fontStyle: "italic",
              fontWeight: 400,
              color: palette.accent,
              marginTop: 34,
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
