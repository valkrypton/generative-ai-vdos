import React from "react";
import { Composition } from "remotion";
import { TitleCard, titleCardDefaults, TitleCardProps } from "./TitleCard";
import { Quote, quoteDefaults, QuoteProps } from "./Quote";
import { LowerThird, lowerThirdDefaults, LowerThirdProps } from "./LowerThird";
import { Outro, outroDefaults, OutroProps } from "./Outro";

const FPS = 30;
const WIDTH = 1920;
const HEIGHT = 1080;

// durationInFrames is passed in via --props by the Python compose stage (derived
// from the scene's narration length). calculateMetadata lets each render size
// itself to that value while keeping a sane default for the Studio preview.
const durationFrom = (props: { durationInFrames?: number }) => ({
  durationInFrames: Math.max(30, Math.round(props.durationInFrames ?? 150)),
});

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="TitleCard"
        component={TitleCard}
        durationInFrames={titleCardDefaults.durationInFrames}
        fps={FPS}
        width={WIDTH}
        height={HEIGHT}
        defaultProps={titleCardDefaults}
        calculateMetadata={({ props }: { props: TitleCardProps }) =>
          durationFrom(props)
        }
      />
      <Composition
        id="Quote"
        component={Quote}
        durationInFrames={quoteDefaults.durationInFrames}
        fps={FPS}
        width={WIDTH}
        height={HEIGHT}
        defaultProps={quoteDefaults}
        calculateMetadata={({ props }: { props: QuoteProps }) =>
          durationFrom(props)
        }
      />
      <Composition
        id="LowerThird"
        component={LowerThird}
        durationInFrames={lowerThirdDefaults.durationInFrames}
        fps={FPS}
        width={WIDTH}
        height={HEIGHT}
        defaultProps={lowerThirdDefaults}
        calculateMetadata={({ props }: { props: LowerThirdProps }) =>
          durationFrom(props)
        }
      />
      <Composition
        id="Outro"
        component={Outro}
        durationInFrames={outroDefaults.durationInFrames}
        fps={FPS}
        width={WIDTH}
        height={HEIGHT}
        defaultProps={outroDefaults}
        calculateMetadata={({ props }: { props: OutroProps }) =>
          durationFrom(props)
        }
      />
    </>
  );
};
