import React from "react";
import {
  AbsoluteFill,
  Freeze,
  Img,
  OffthreadVideo,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { ScreenFocus } from "../types";
import { BLUE, CYAN, GRADIENT_TITLE, IS_LIGHT, IS_PORTRAIT, IS_QUANTUM, MUTED, TEXT, THEME, VIOLET } from "./deckContext";

export const EmbossedTitle: React.FC<{
  children: React.ReactNode;
  fontSize: number;
  lineHeight?: number;
  opacity?: number;
}> = ({ children, fontSize, lineHeight = 1.06, opacity = 1 }) => {
  const depthShadow = IS_LIGHT
    ? "0 2px 0 rgba(15,23,42,0.14), 0 8px 18px rgba(15,23,42,0.16)"
    : `0 1px 0 #0a2540, 0 2px 0 #091d38, 0 3px 0 #07162e, 0 4px 0 #050e22, 0 6px 0 #030714, 0 14px 28px rgba(0,0,0,0.88), 0 0 28px ${CYAN}55`;
  return (
    <div style={{ position: "relative", display: "inline-block", opacity }}>
      {/* Extruded 3D depth + lift shadow layer */}
      <div
        aria-hidden
        style={{
          fontSize,
          fontWeight: 900,
          lineHeight,
          letterSpacing: "-0.015em",
          color: "transparent",
          textShadow: depthShadow,
          userSelect: "none",
        }}
      >
        {children}
      </div>
      {/* Bright crisp foreground gradient face */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          fontSize,
          fontWeight: 900,
          lineHeight,
          letterSpacing: "-0.015em",
          ...GRADIENT_TITLE,
          filter: IS_LIGHT ? "none" : `drop-shadow(0 0 12px ${CYAN}40)`,
        }}
      >
        {children}
      </div>
    </div>
  );
};

// Deterministic stars for deep-space backdrop

export const parseKpiValue = (raw: string): { prefix: string; num: number; suffix: string; grouped: boolean } | null => {
  if (/[.,/–-]\d/.test(raw)) return null;
  const m = raw.match(/^(\D*?)(\d[\d ]*\d|\d)(\D*)$/);
  if (!m) return null;
  const digits = m[2].replace(/ /g, "");
  const num = Number(digits);
  if (!Number.isFinite(num)) return null;
  return { prefix: m[1], num, suffix: m[3], grouped: num >= 1000 };
};

export const AnimatedKpiValue: React.FC<{ value: string; startFrame: number; durationFrames?: number }> = ({
  value,
  startFrame,
  durationFrames = 40,
}) => {
  const frame = useCurrentFrame();
  const parsed = parseKpiValue(value);
  if (!parsed) return <>{value}</>;
  const p = interpolate(frame, [startFrame, startFrame + durationFrames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const eased = 1 - Math.pow(1 - p, 3);
  const current = Math.round(parsed.num * eased);
  const text = parsed.grouped ? current.toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ") : current.toString();
  return <>{`${parsed.prefix}${text}${parsed.suffix}`}</>;
};

// Spinning 3D Earth-Radar + orbiting Top-100 coins + deep-space starfield & background crypto chart

export const SlideChrome: React.FC<{
  brand: string;
  num: string;
  tag: string;
  dur: number;
  hasTransition?: boolean;
  children: React.ReactNode;
}> = ({ brand, num, tag, dur, hasTransition = false, children }) => {
  const frame = useCurrentFrame();
  const fadeIn = hasTransition ? 1 : interpolate(frame, [0, 14], [0, 1], { extrapolateRight: "clamp" });
  const fadeOut = hasTransition
    ? 1
    : interpolate(frame, [dur - 14, dur], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const slideX = interpolate(frame, [0, 14], [hasTransition ? 14 : 28, 0], { extrapolateRight: "clamp" });
  const opacity = Math.min(fadeIn, fadeOut);
  const pad = IS_PORTRAIT ? "48px 54px 160px 54px" : "40px 78px 110px 78px";

  return (
    <AbsoluteFill
      style={{
        opacity,
        transform: `translateX(${slideX}px)`,
        fontFamily: "Segoe UI, Inter, Arial, sans-serif",
        padding: pad,
        display: "flex",
        flexDirection: "column",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: IS_PORTRAIT ? 28 : 22,
          borderBottom: `1px solid ${THEME.cardBorder}`,
          paddingBottom: 14,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <div style={{ width: 16, height: 16, borderRadius: 5, background: `linear-gradient(135deg, ${CYAN}, ${BLUE}, ${VIOLET})`, boxShadow: `0 0 16px ${CYAN}` }} />
          <span style={{ fontSize: IS_PORTRAIT ? 20 : 22, fontWeight: 800, color: TEXT, letterSpacing: 3 }}>{brand}</span>
          <span
            style={{
              marginLeft: 8,
              padding: "5px 14px",
              borderRadius: 999,
              background: THEME.cardBg,
              border: `1px solid ${CYAN}`,
              color: CYAN,
              fontSize: 15,
              fontWeight: 700,
              letterSpacing: 2,
            }}
          >
            {tag}
          </span>
        </div>
        <div style={{ fontSize: 19, fontWeight: 700, color: BLUE, letterSpacing: 2 }}>{num}</div>
      </div>

      <div style={{ flex: 1, display: "flex", alignItems: "center" }}>{children}</div>
    </AbsoluteFill>
  );
};

export const BulletItem: React.FC<{ title: string; desc: string; delay: number; accent?: string }> = ({
  title,
  desc,
  delay,
  accent = CYAN,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - delay, fps, config: { damping: 180 } });
  const y = interpolate(s, [0, 1], [22, 0]);
  return (
    <div
      style={{
        opacity: s,
        transform: `translateY(${y}px)`,
        display: "flex",
        gap: 16,
        alignItems: "flex-start",
        padding: IS_PORTRAIT ? "14px 18px" : "15px 20px",
        borderRadius: IS_QUANTUM ? 20 : 16,
        background: IS_QUANTUM
          ? `radial-gradient(ellipse at 50% -15%, rgba(255,255,255,0.18) 0%, transparent 52%), radial-gradient(ellipse at 50% 120%, ${accent}30 0%, transparent 58%), linear-gradient(155deg, ${accent}22 0%, rgba(8,18,46,0.92) 60%, rgba(3,8,24,0.96) 100%)`
          : THEME.cardBg,
        border: `${IS_QUANTUM ? 1.5 : 1}px solid ${IS_QUANTUM ? `${accent}77` : THEME.cardBorder}`,
        borderTop: `2px solid ${accent}${IS_QUANTUM ? "dd" : "88"}`,
        boxShadow: IS_LIGHT
          ? "0 10px 26px rgba(15,23,42,0.12)"
          : IS_QUANTUM
          ? `0 7px 0 rgba(3,8,22,0.95), 0 10px 0 ${accent}44, 0 22px 44px rgba(0,0,0,0.72), 0 0 28px ${accent}2a, inset 0 2px 3px rgba(255,255,255,0.26), inset 0 -6px 14px rgba(0,0,0,0.48)`
          : `0 16px 38px rgba(0,0,0,0.52), inset 0 1px 0 rgba(255,255,255,0.10)`,
      }}
    >
      <div style={{ width: 12, height: 12, marginTop: 9, borderRadius: "50%", backgroundColor: accent, boxShadow: `0 0 16px ${accent}`, flexShrink: 0 }} />
      <div>
        <div
          style={{
            fontSize: IS_PORTRAIT ? 25 : 26,
            fontWeight: IS_QUANTUM ? 900 : 800,
            color: IS_QUANTUM ? "#ffffff" : TEXT,
            textShadow: IS_LIGHT
              ? "none"
              : IS_QUANTUM
              ? `0 2px 0 #050d20, 0 4px 0 #020714, 0 10px 18px rgba(0,0,0,0.92), 0 0 18px ${accent}99`
              : "0 2px 8px rgba(0,0,0,0.75)",
          }}
        >
          {title}
        </div>
        <div style={{ fontSize: IS_PORTRAIT ? 19 : 19, color: MUTED, marginTop: 4, lineHeight: 1.35 }}>{desc}</div>
      </div>
    </div>
  );
};

export const CodeWindow3D: React.FC<{ filename: string; lines: { text: string; color?: string }[]; delay?: number }> = ({
  filename,
  lines,
  delay = 12,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - delay, fps, config: { damping: 170 } });
  const rotY = IS_PORTRAIT ? 0 : interpolate(s, [0, 1], [-22, -8]) + Math.sin(frame / 45) * 2.4;
  const rotX = IS_PORTRAIT ? 0 : 4 + Math.cos(frame / 55) * 1.8;
  const floatY = Math.sin(frame / 36) * 5;

  return (
    <div style={{ width: "100%", perspective: 1500, position: "relative" }}>
      <div
        style={{
          opacity: s,
          transformStyle: "preserve-3d",
          transform: `translateY(${floatY}px) rotateY(${rotY}deg) rotateX(${rotX}deg)`,
          position: "relative",
        }}
      >
        {/* 3D floating wireframe backplate behind the code window */}
        <div
          style={{
            position: "absolute",
            inset: -12,
            borderRadius: 24,
            border: `1.5px solid ${VIOLET}66`,
            background: `linear-gradient(135deg, ${BLUE}14, ${VIOLET}10)`,
            transform: "translateZ(-36px) translateX(16px) translateY(14px)",
            boxShadow: `0 0 40px ${BLUE}25`,
            pointerEvents: "none",
          }}
        />
        <div
          style={{
            borderRadius: 20,
            overflow: "hidden",
            border: `1.5px solid ${BLUE}`,
            background: THEME.codeBg,
            boxShadow: `0 28px 75px rgba(0,0,0,0.6), 0 0 28px ${BLUE}28`,
          }}
        >
          <div style={{ height: 42, background: THEME.codeHeaderBg, borderBottom: "1px solid rgba(255,255,255,0.10)", display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 16px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div style={{ width: 11, height: 11, borderRadius: "50%", background: "#ff5f56" }} />
              <div style={{ width: 11, height: 11, borderRadius: "50%", background: "#ffbd2e" }} />
              <div style={{ width: 11, height: 11, borderRadius: "50%", background: "#27c93f" }} />
              <div style={{ marginLeft: 10, fontSize: 16, color: "#e2e8f0", fontFamily: "Consolas, monospace" }}>{filename}</div>
            </div>
            <div style={{ fontSize: 12, fontFamily: "Consolas, monospace", color: CYAN, letterSpacing: 2, opacity: 0.85 }}>SOURCE</div>
          </div>
          <div style={{ padding: IS_PORTRAIT ? "18px 20px" : "22px 26px", fontFamily: "Consolas, 'Cascadia Code', monospace", fontSize: IS_PORTRAIT ? 18 : 20, lineHeight: 1.5 }}>
            {lines.map((line, i) => {
              const lineOpacity = interpolate(frame, [delay + 6 + i * 3, delay + 14 + i * 3], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
              return (
                <div key={i} style={{ opacity: lineOpacity, display: "flex", gap: 14 }}>
                  <span style={{ color: "#64748b", minWidth: 26, textAlign: "right" }}>{i + 1}</span>
                  <span style={{ color: line.color ?? "#e2e8f0", whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{line.text}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};

export const ScreenWindow3D: React.FC<{
  src: string;
  caption: string;
  focus?: ScreenFocus;
  maxHeight?: number;
  delay?: number;
  isVideo?: boolean;
  videoDurationSec?: number;
}> = ({
  src,
  caption,
  focus,
  maxHeight = IS_PORTRAIT ? 640 : 610,
  delay = 10,
  isVideo = false,
  videoDurationSec = 0,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const videoFrames = videoDurationSec > 0 ? Math.max(1, Math.round(videoDurationSec * fps)) : 0;
  const s = spring({ frame: frame - delay, fps, config: { damping: 165 } });
  const rotY = IS_PORTRAIT ? 0 : interpolate(s, [0, 1], [-22, -7]) + Math.sin(frame / 46) * 2.4;
  const rotX = IS_PORTRAIT ? 0 : 3.5 + Math.cos(frame / 54) * 1.6;
  const floatY = Math.sin(frame / 34) * 6;
  // Virtual Director Camera auto-zoom toward focus point when provided (Screen Studio style)
  const targetZoom = focus ? Math.min(2.2, Math.max(1.1, focus.zoom ?? 1.48)) : 1.045;
  const zoomIn = focus ? spring({ frame: Math.max(0, frame - 28), fps, config: { damping: 130, stiffness: 80 } }) : 0;
  const scale = focus
    ? interpolate(zoomIn, [0, 1], [1.0, targetZoom], { extrapolateRight: "clamp" })
    : interpolate(frame, [0, 360], [1.0, 1.045], { extrapolateRight: "clamp" });
  const fxPct = focus ? Math.min(92, Math.max(8, focus.x * 100)) : 50;
  const fyPct = focus ? Math.min(92, Math.max(8, focus.y * 100)) : 0;
  const origin = focus ? `${fxPct.toFixed(1)}% ${fyPct.toFixed(1)}%` : "center top";
  // Subtle glass reflection sweep every 120 frames
  const sweepPct = ((frame * 1.9) % 240) - 40;

  return (
    <div style={{ width: "100%", perspective: 1500, position: "relative" }}>
      {/* Soft 3D holographic glow aura behind the monitor */}
      <div
        style={{
          position: "absolute",
          left: "8%",
          right: "8%",
          bottom: -34,
          height: 36,
          borderRadius: "50%",
          background: `radial-gradient(ellipse, ${CYAN}55 0%, ${BLUE}22 50%, transparent 75%)`,
          filter: "blur(14px)",
          pointerEvents: "none",
        }}
      />
      <div
        style={{
          opacity: s,
          transformStyle: "preserve-3d",
          transform: `translateY(${floatY}px) rotateY(${rotY}deg) rotateX(${rotX}deg)`,
          position: "relative",
        }}
      >
        {/* Layered 3D depth backplate behind the screen */}
        <div
          style={{
            position: "absolute",
            inset: -14,
            borderRadius: 24,
            border: `1.5px solid ${CYAN}55`,
            background: `linear-gradient(135deg, ${CYAN}12, ${VIOLET}12)`,
            transform: "translateZ(-42px) translateX(18px) translateY(16px)",
            boxShadow: `0 0 46px ${CYAN}22`,
            pointerEvents: "none",
          }}
        />
        {/* Secondary 3D accent frame */}
        <div
          style={{
            position: "absolute",
            inset: -6,
            borderRadius: 22,
            border: `1px dashed ${BLUE}44`,
            transform: "translateZ(-20px) translateX(8px) translateY(8px)",
            pointerEvents: "none",
          }}
        />
        <div
          style={{
            borderRadius: 20,
            overflow: "hidden",
            border: `1.5px solid ${CYAN}`,
            background: THEME.codeBg,
            boxShadow: `0 30px 80px rgba(0,0,0,0.65), 0 0 32px ${CYAN}30`,
            position: "relative",
          }}
        >
          <div style={{ height: 40, background: THEME.codeHeaderBg, borderBottom: "1px solid rgba(255,255,255,0.12)", display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 16px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div style={{ width: 11, height: 11, borderRadius: "50%", background: "#ff5f56" }} />
              <div style={{ width: 11, height: 11, borderRadius: "50%", background: "#ffbd2e" }} />
              <div style={{ width: 11, height: 11, borderRadius: "50%", background: "#27c93f" }} />
              <div style={{ marginLeft: 10, fontSize: 15, color: "#e2e8f0", fontWeight: 600 }}>{caption}</div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 7, padding: "3px 10px", borderRadius: 999, background: `${CYAN}1a`, border: `1px solid ${CYAN}88` }}>
              <div style={{ width: 7, height: 7, borderRadius: "50%", background: CYAN, boxShadow: `0 0 10px ${CYAN}`, opacity: 0.65 + Math.sin(frame / 10) * 0.35 }} />
              <span style={{ fontSize: 11, fontFamily: "Consolas, monospace", color: CYAN, fontWeight: 700, letterSpacing: 1.5 }}>LIVE UI</span>
            </div>
          </div>
          <div style={{ overflow: "hidden", maxHeight, position: "relative" }}>
            {isVideo ? (
              // Recording is a silent clip, frame-synced to the slide. When the slide outlasts the clip,
              // Freeze holds its last frame instead of rendering a blank frame.
              <Freeze frame={Math.max(0, videoFrames - 1)} active={videoFrames > 0 && frame >= videoFrames}>
                <OffthreadVideo
                  src={staticFile(src)}
                  muted
                  style={{ width: "100%", height: "auto", display: "block", transform: `scale(${scale})`, transformOrigin: origin }}
                />
              </Freeze>
            ) : (
              <Img src={staticFile(src)} style={{ width: "100%", height: "auto", display: "block", transform: `scale(${scale})`, transformOrigin: origin }} />
            )}
            {focus && zoomIn > 0.15 && (
              <div
                style={{
                  position: "absolute",
                  left: `${fxPct}%`,
                  top: `${fyPct}%`,
                  width: 52,
                  height: 52,
                  marginLeft: -26,
                  marginTop: -26,
                  borderRadius: "50%",
                  border: `2.5px solid ${CYAN}`,
                  boxShadow: `0 0 24px ${CYAN}, inset 0 0 14px ${CYAN}55`,
                  opacity: Math.min(0.85, zoomIn) * (0.65 + 0.35 * Math.sin(frame / 8)),
                  pointerEvents: "none",
                }}
              />
            )}
            {/* Animated subtle glass sweep sheen */}
            <div
              style={{
                position: "absolute",
                inset: 0,
                background: `linear-gradient(112deg, transparent ${sweepPct - 12}%, rgba(255,255,255,0.09) ${sweepPct}%, transparent ${sweepPct + 12}%)`,
                pointerEvents: "none",
              }}
            />
          </div>
        </div>
      </div>
    </div>
  );
};

/* ---------- GENERIC SLIDE TEMPLATES ---------- */

export const TerminalWindow: React.FC<{ filename: string; lines: { text: string; color?: string }[] }> = ({ filename, lines }) => {
  const frame = useCurrentFrame();
  let budget = Math.max(0, (frame - 16) * 1.25);
  const typed = lines.map((l) => {
    const take = Math.max(0, Math.min(l.text.length, Math.floor(budget)));
    budget -= l.text.length + 1;
    return take;
  });
  const activeIdx = typed.findIndex((t, i) => t < lines[i].text.length);
  const cursorOn = Math.floor(frame / 15) % 2 === 0;
  return (
    <div style={{ width: "100%", borderRadius: 20, overflow: "hidden", border: `1px solid ${CYAN}`, background: THEME.codeBg, boxShadow: "0 26px 70px rgba(0,0,0,0.55)" }}>
      <div style={{ height: 40, background: THEME.codeHeaderBg, borderBottom: "1px solid rgba(255,255,255,0.10)", display: "flex", alignItems: "center", padding: "0 16px", gap: 8 }}>
        <div style={{ width: 11, height: 11, borderRadius: "50%", background: "#ff5f56" }} />
        <div style={{ width: 11, height: 11, borderRadius: "50%", background: "#ffbd2e" }} />
        <div style={{ width: 11, height: 11, borderRadius: "50%", background: "#27c93f" }} />
        <div style={{ marginLeft: 10, fontSize: 16, color: "#e2e8f0", fontFamily: "Consolas, monospace" }}>terminal · {filename}</div>
      </div>
      <div style={{ padding: IS_PORTRAIT ? "18px 20px" : "22px 26px", fontFamily: "Consolas, 'Cascadia Code', monospace", fontSize: IS_PORTRAIT ? 18 : 20, lineHeight: 1.5, minHeight: IS_PORTRAIT ? 360 : 300 }}>
        {lines.map((line, i) => {
          if (typed[i] === 0 && i !== activeIdx) return null;
          const isActive = i === activeIdx || (activeIdx === -1 && i === lines.length - 1);
          return (
            <div key={i} style={{ display: "flex", gap: 12 }}>
              <span style={{ color: "#4ade80", minWidth: 18 }}>$</span>
              <span style={{ color: line.color ?? "#e2e8f0", whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                {line.text.slice(0, typed[i])}
              </span>
              {isActive && cursorOn && <span style={{ display: "inline-block", width: 11, height: 22, background: "#e2e8f0", marginTop: 3 }} />}
            </div>
          );
        })}
      </div>
    </div>
  );
};
