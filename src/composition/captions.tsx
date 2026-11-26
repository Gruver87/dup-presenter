import React from "react";
import {
  useCurrentFrame,
} from "remotion";
import { CaptionCue } from "../types";
import { BLUE, CYAN, DURATION, FPS, IS_PORTRAIT, PINK, THEME, VIOLET } from "./deckContext";

export const captionWrapStyle = (): React.CSSProperties => ({
  position: "absolute",
  left: IS_PORTRAIT ? 40 : 120,
  right: IS_PORTRAIT ? 40 : 120,
  bottom: IS_PORTRAIT ? 48 : 26,
  display: "flex",
  justifyContent: "center",
  pointerEvents: "none",
});

export const CaptionKaraokeLayer: React.FC<{ cue: CaptionCue; sec: number }> = ({ cue, sec }) => {
  const words = cue.words ?? [];
  return (
    <div style={captionWrapStyle()}>
      <div
        style={{
          background: THEME.captionBg,
          color: THEME.captionText,
          padding: IS_PORTRAIT ? "14px 22px" : "10px 22px",
          borderRadius: 14,
          border: `1px solid ${THEME.cardBorder}`,
          fontFamily: "Segoe UI, Inter, Arial, sans-serif",
          fontSize: IS_PORTRAIT ? 28 : 24,
          fontWeight: 700,
          lineHeight: 1.32,
          textAlign: "center",
          maxWidth: "100%",
          boxShadow: "0 12px 30px rgba(0,0,0,0.45)",
        }}
      >
        {cue.speaker && (
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              padding: "2px 10px",
              borderRadius: 999,
              marginRight: 10,
              background: cue.speaker === "B" ? `${PINK}28` : `${CYAN}24`,
              border: `1px solid ${cue.speaker === "B" ? PINK : CYAN}`,
              color: cue.speaker === "B" ? PINK : CYAN,
              fontFamily: "Consolas, monospace",
              fontSize: IS_PORTRAIT ? 20 : 17,
              fontWeight: 900,
              verticalAlign: "middle",
            }}
          >
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: cue.speaker === "B" ? PINK : CYAN,
                boxShadow: `0 0 10px ${cue.speaker === "B" ? PINK : CYAN}`,
              }}
            />
            {cue.speaker === "A" ? "HOST" : cue.speaker === "B" ? "EXPERT" : cue.speaker}
          </span>
        )}
        {words.map((w, i) => {
          const current = sec >= w.start && sec < w.end;
          const spoken = sec >= w.end;
          return (
            <span
              key={`${i}-${w.start}`}
              style={{
                color: current ? CYAN : spoken ? THEME.captionText : "rgba(226,232,240,0.45)",
                textShadow: current ? `0 0 14px ${CYAN}` : undefined,
              }}
            >
              {w.w}
              {i < words.length - 1 ? " " : ""}
            </span>
          );
        })}
      </div>
    </div>
  );
};

export const DuoSpeakerChip: React.FC<{ speaker: string; large?: boolean }> = ({ speaker, large = false }) => {
  const col = speaker === "B" ? PINK : CYAN;
  const label = speaker === "A" ? "HOST" : speaker === "B" ? "EXPERT" : speaker;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: large ? "4px 14px" : "2px 10px",
        borderRadius: 999,
        marginRight: large ? 14 : 10,
        background: `${col}26`,
        border: `1.5px solid ${col}`,
        color: col,
        fontFamily: "Consolas, monospace",
        fontSize: large ? (IS_PORTRAIT ? 26 : 22) : IS_PORTRAIT ? 20 : 17,
        fontWeight: 900,
        verticalAlign: "middle",
      }}
    >
      <span
        style={{
          width: large ? 10 : 8,
          height: large ? 10 : 8,
          borderRadius: "50%",
          background: col,
          boxShadow: `0 0 10px ${col}`,
        }}
      />
      {label}
    </span>
  );
};

export const CaptionBoldLayer: React.FC<{ cue: CaptionCue }> = ({ cue }) => (
  <div style={captionWrapStyle()}>
    <div
      style={{
        color: "#ffffff",
        fontFamily: "Segoe UI Black, Segoe UI, Inter, Arial, sans-serif",
        fontSize: IS_PORTRAIT ? 58 : 46,
        fontWeight: 900,
        lineHeight: 1.12,
        textAlign: "center",
        maxWidth: "100%",
        textShadow: "0 0 4px #000, 0 0 10px #000, 0 4px 18px rgba(0,0,0,0.9)",
      }}
    >
      {cue.speaker && <DuoSpeakerChip speaker={cue.speaker} large />}
      {cue.text}
    </div>
  </div>
);

export const CaptionOverlay: React.FC<{ captions?: CaptionCue[]; style?: "box" | "karaoke" | "bold" }> = ({
  captions,
  style = "box",
}) => {
  const frame = useCurrentFrame();
  if (!captions || captions.length === 0) return null;
  const sec = frame / FPS;
  const cue = captions.find((c) => sec >= c.start_sec && sec <= c.end_sec);
  if (!cue) return null;
  if (style === "bold") return <CaptionBoldLayer cue={cue} />;
  // Every voiced cue carries word timings (audio_fx.build_word_captions). A cue without them is a defensive case, shown as box.
  if (style === "karaoke" && cue.words && cue.words.length > 0) return <CaptionKaraokeLayer cue={cue} sec={sec} />;
  return <CaptionOverlayBox captions={captions} />;
};

export const CaptionOverlayBox: React.FC<{ captions?: CaptionCue[] }> = ({ captions }) => {
  const frame = useCurrentFrame();
  if (!captions || captions.length === 0) return null;
  const sec = frame / FPS;
  const active = captions.find((c) => sec >= c.start_sec && sec <= c.end_sec);
  if (!active) return null;

  return (
    <div
      style={{
        position: "absolute",
        left: IS_PORTRAIT ? 40 : 120,
        right: IS_PORTRAIT ? 40 : 120,
        bottom: IS_PORTRAIT ? 48 : 26,
        display: "flex",
        justifyContent: "center",
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          background: THEME.captionBg,
          color: THEME.captionText,
          padding: IS_PORTRAIT ? "14px 22px" : "10px 22px",
          borderRadius: 14,
          border: `1px solid ${THEME.cardBorder}`,
          fontFamily: "Segoe UI, Inter, Arial, sans-serif",
          fontSize: IS_PORTRAIT ? 28 : 24,
          fontWeight: 600,
          lineHeight: 1.32,
          textAlign: "center",
          maxWidth: "100%",
          boxShadow: "0 12px 30px rgba(0,0,0,0.45)",
        }}
      >
        {active.speaker && <DuoSpeakerChip speaker={active.speaker} />}
        {active.text}
      </div>
    </div>
  );
};

export const ProgressBar: React.FC = () => {
  const frame = useCurrentFrame();
  const pct = (frame / Math.max(1, DURATION)) * 100;
  return (
    <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 7, background: "rgba(255,255,255,0.08)" }}>
      <div style={{ width: `${pct}%`, height: "100%", background: `linear-gradient(90deg, ${CYAN}, ${BLUE}, ${VIOLET}, ${PINK})`, boxShadow: `0 0 16px ${CYAN}` }} />
    </div>
  );
};

// Free stock clip behind a slide (Pexels / Pixabay). Dimmed by theme bg so text stays readable.
