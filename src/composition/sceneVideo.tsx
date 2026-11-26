import React from "react";
import { OffthreadVideo, VolumeProp } from "remotion";
import { Video as MediaVideo, VideoObjectFit } from "@remotion/media";
import { DECK } from "./deckContext";

/**
 * Video element for cinema clip shots. The engine is chosen per deck by `media_engine`:
 * - "offthread" (default): Remotion OffthreadVideo, exactly the previous behaviour.
 * - "media": @remotion/media Video. `disallowFallbackToOffthreadVideo` is set, so a decode failure
 *   fails the render instead of silently switching engines (fail-closed A/B).
 * Both engines take `trimBefore` in frames and `volume` as a function, so call sites are unchanged.
 */
export type SceneVideoProps = {
  src: string;
  trimBefore?: number;
  durationInFrames?: number;
  playbackRate?: number;
  muted?: boolean;
  volume?: VolumeProp;
  style?: React.CSSProperties;
};

export const SceneVideo: React.FC<SceneVideoProps> = ({
  src,
  trimBefore,
  durationInFrames,
  playbackRate,
  muted,
  volume,
  style,
}) => {
  if (DECK.media_engine === "media") {
    // @remotion/media takes objectFit as a prop (style.objectFit logs a warning per tab).
    const { objectFit, ...restStyle } = style ?? {};
    return (
      <MediaVideo
        src={src}
        trimBefore={trimBefore}
        playbackRate={playbackRate}
        muted={muted}
        volume={volume}
        objectFit={objectFit as VideoObjectFit | undefined}
        style={restStyle}
        disallowFallbackToOffthreadVideo
      />
    );
  }
  return (
    <OffthreadVideo
      src={src}
      trimBefore={trimBefore}
      durationInFrames={durationInFrames}
      playbackRate={playbackRate}
      muted={muted}
      volume={volume}
      style={style}
    />
  );
};
