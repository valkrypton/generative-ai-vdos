import React from "react";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { DEFAULT_PALETTE, Palette, serifStack } from "./theme";

export type QuoteProps = {
  heading: string; // the quote text
  attribution: string | null; // e.g. "— Rumi"
  palette: Palette;
  durationInFrames: number;
};

export const quoteDefaults: QuoteProps = {
  heading: "Yesterday I was clever, so I wanted to change the world.",
  attribution: "— Rumi",
  palette: DEFAULT_PALETTE,
  durationInFrames: 180,
};

export const Quote: React.FC<QuoteProps> = ({
  heading,
  attribution,
  palette,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const enter = spring({ frame, fps, config: { damping: 200 } });
  const quoteOpacity = interpolate(enter, [0, 1], [0, 1]);
  // Settle inward: start slightly larger, ease to 1.
  const quoteScale = interpolate(enter, [0, 1], [1.05, 1]);

  const attribOpacity = interpolate(frame, [22, 44], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const exit = interpolate(
    frame,
    [durationInFrames - 14, durationInFrames],
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
          background: `radial-gradient(circle at 50% 58%, ${palette.glow} 0%, rgba(0,0,0,0) 58%)`,
          transform: `scale(${glowScale})`,
        }}
      />
      <AbsoluteFill
        style={{
          justifyContent: "center",
          alignItems: "center",
          flexDirection: "column",
          padding: "0 200px",
          textAlign: "center",
        }}
      >
        <div
          style={{
            fontFamily: serifStack,
            fontSize: 150,
            lineHeight: 0.6,
            color: palette.accent,
            opacity: 0.55,
            marginBottom: 10,
          }}
        >
          &ldquo;
        </div>
        <div
          style={{
            fontFamily: serifStack,
            fontSize: 68,
            lineHeight: 1.34,
            fontStyle: "italic",
            fontWeight: 400,
            color: palette.fg,
            transform: `scale(${quoteScale})`,
            opacity: quoteOpacity,
            textShadow: "0 6px 40px rgba(10,6,18,0.6)",
          }}
        >
          {heading}
        </div>
        {attribution ? (
          <div
            style={{
              fontFamily: serifStack,
              fontSize: 40,
              fontWeight: 400,
              color: palette.accent,
              marginTop: 48,
              letterSpacing: 3,
              opacity: attribOpacity,
            }}
          >
            {attribution}
          </div>
        ) : null}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
