import React from "react";
import {
  AbsoluteFill,
  OffthreadVideo,
  interpolate,
  staticFile,
  useCurrentFrame,
} from "remotion";
import { ResolvedSlide } from "../types";
import { THEME } from "./deckContext";

export const StockBackdrop: React.FC<{ slide: ResolvedSlide; dur: number }> = ({ slide, dur }) => {
  const frame = useCurrentFrame();
  if (!slide.media) return null;
  const scale = interpolate(frame, [0, Math.max(1, dur)], [1.0, 1.07], { extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ overflow: "hidden" }}>
      <AbsoluteFill style={{ transform: `scale(${scale})` }}>
        <OffthreadVideo
          src={staticFile(slide.media.video_file)}
          muted
          style={{ width: "100%", height: "100%", objectFit: "cover", opacity: 0.45 }}
        />
      </AbsoluteFill>
      <AbsoluteFill style={{ background: `linear-gradient(180deg, ${THEME.bg}bf 0%, ${THEME.bg}e6 100%)` }} />
      <div
        style={{
          position: "absolute",
          right: 28,
          bottom: 22,
          fontSize: 16,
          color: THEME.muted,
          opacity: 0.75,
          fontFamily: "Consolas, monospace",
        }}
      >
        {slide.media.credit}
      </div>
    </AbsoluteFill>
  );
};
