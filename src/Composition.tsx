import React from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  OffthreadVideo,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { CalculateMetadataFunction, Composition } from "remotion";
import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { slide as slideTransition } from "@remotion/transitions/slide";
import { wipe } from "@remotion/transitions/wipe";
import rawDeck from "./generated/deck_resolved.json";
import { resolveTheme } from "./themes";
import type { CaptionCue, ResolvedDeck, ResolvedSlide, ScreenFocus } from "./types";

const DECK = rawDeck as unknown as ResolvedDeck;
const THEME = resolveTheme(DECK.theme);
const FPS = DECK.fps || 30;
const WIDTH = DECK.width || 1920;
const HEIGHT = DECK.height || 1080;
const IS_PORTRAIT = HEIGHT > WIDTH;
const TRANSITION_STYLE = DECK.transition_style ?? "fade";
const TRANSITION_FRAMES =
  TRANSITION_STYLE === "none" || DECK.slides.length < 2
    ? 0
    : Math.max(0, Math.min(24, DECK.transition_frames ?? 12));
const COMPUTED_TOTAL_FRAMES =
  DECK.slides.reduce((acc, s) => acc + Math.max(1, Math.round(s.duration_sec * FPS)), 0) -
  Math.max(0, DECK.slides.length - 1) * TRANSITION_FRAMES;
const DURATION = Math.max(1, DECK.total_frames ?? COMPUTED_TOTAL_FRAMES);

// Precompute global [startSec, endSec] speech intervals across all slides for smooth music ducking.
const GLOBAL_SPEECH_WINDOWS: [number, number][] = (() => {
  const out: [number, number][] = [];
  let cursorFrames = 0;
  for (let i = 0; i < DECK.slides.length; i++) {
    const s = DECK.slides[i];
    const slideStartSec = s.start_sec ?? cursorFrames / FPS;
    const wins = s.speech_windows;
    if (wins && wins.length > 0) {
      for (const [w0, w1] of wins) {
        out.push([slideStartSec + w0, slideStartSec + w1]);
      }
    } else if (s.captions && s.captions.length > 0) {
      for (const c of s.captions) {
        out.push([slideStartSec + c.start_sec, slideStartSec + c.end_sec]);
      }
    }
    cursorFrames += Math.max(1, Math.round(s.duration_sec * FPS)) - TRANSITION_FRAMES;
  }
  return out;
})();

const computeDuckFactor = (frame: number, duckRatio: number): number => {
  if (GLOBAL_SPEECH_WINDOWS.length === 0 || duckRatio >= 0.999) return 1.0;
  const t = frame / FPS;
  const attack = 0.22;
  const release = 0.42;
  let maxDepth = 0;
  for (let i = 0; i < GLOBAL_SPEECH_WINDOWS.length; i++) {
    const [s, e] = GLOBAL_SPEECH_WINDOWS[i];
    if (t >= s && t <= e) {
      return duckRatio;
    }
    if (t >= s - attack && t < s) {
      const p = (t - (s - attack)) / attack;
      if (p > maxDepth) maxDepth = p;
    } else if (t > e && t <= e + release) {
      const p = 1 - (t - e) / release;
      if (p > maxDepth) maxDepth = p;
    }
  }
  return 1.0 - maxDepth * (1.0 - duckRatio);
};

type Props = Record<string, unknown>;

const calculateMetadata: CalculateMetadataFunction<Props> = () => ({
  durationInFrames: DURATION,
  fps: FPS,
  width: WIDTH,
  height: HEIGHT,
});

const BG = THEME.bg;
const CYAN = THEME.accent1;
const BLUE = THEME.accent2;
const VIOLET = THEME.accent3;
const PINK = THEME.accent4;
const TEXT = THEME.text;
const MUTED = THEME.muted;

const GRADIENT_TITLE: React.CSSProperties = {
  background: `linear-gradient(95deg, ${CYAN} 0%, ${BLUE} 48%, ${VIOLET} 100%)`,
  WebkitBackgroundClip: "text",
  WebkitTextFillColor: "transparent",
};

const PARTICLES = Array.from({ length: 28 }, (_, i) => ({
  x: ((i * 197 + 83) % Math.max(200, WIDTH - 80)) + 40,
  y: ((i * 131 + 59) % Math.max(200, HEIGHT - 100)) + 50,
  r: (i % 3) * 2.2 + 2.5,
  speed: 0.35 + (i % 5) * 0.22,
  color: [CYAN, BLUE, VIOLET, PINK][i % 4],
}));

const HEX_SHARDS = Array.from({ length: 8 }, (_, i) => ({
  x: ((i * 271 + 140) % Math.max(300, WIDTH - 200)) + 100,
  y: ((i * 173 + 110) % Math.max(300, HEIGHT - 200)) + 100,
  size: 44 + (i % 4) * 18,
  speed: 0.5 + (i % 3) * 0.3,
  color: [CYAN, BLUE, VIOLET, PINK][i % 4],
}));

const Aurora3DBackdrop: React.FC = () => {
  const frame = useCurrentFrame();
  const gridShift = (frame * 2.6) % 80;
  const radarAngle = (frame * 1.35) % 360;

  const liveParticles = PARTICLES.map((p, idx) => {
    const span = HEIGHT + 120;
    const py = ((p.y - frame * p.speed + span * 2) % span) - 20;
    const px = p.x + Math.sin((frame + idx * 20) / 45) * 22;
    return { ...p, px, py };
  });

  // Connect nearby particles into a subtle 3D-feeling data mesh behind the content
  const meshLinks: { x1: number; y1: number; x2: number; y2: number; op: number; color: string }[] = [];
  for (let i = 0; i < liveParticles.length; i++) {
    for (let j = i + 1; j < liveParticles.length; j++) {
      const dx = liveParticles[i].px - liveParticles[j].px;
      const dy = liveParticles[i].py - liveParticles[j].py;
      const d = Math.hypot(dx, dy);
      if (d < 240) {
        meshLinks.push({
          x1: liveParticles[i].px,
          y1: liveParticles[i].py,
          x2: liveParticles[j].px,
          y2: liveParticles[j].py,
          op: (1 - d / 240) * 0.24,
          color: liveParticles[i].color,
        });
      }
    }
  }

  return (
    <AbsoluteFill style={{ backgroundColor: BG, overflow: "hidden" }}>
      {/* Soft aurora volume lights */}
      <div
        style={{
          position: "absolute",
          width: 1020,
          height: 1020,
          borderRadius: "50%",
          background: `radial-gradient(circle, ${THEME.glow1} 0%, transparent 72%)`,
          left: -140 + Math.sin(frame / 75) * 90,
          top: -220 + Math.cos(frame / 90) * 60,
          filter: "blur(32px)",
        }}
      />
      <div
        style={{
          position: "absolute",
          width: 1080,
          height: 1080,
          borderRadius: "50%",
          background: `radial-gradient(circle, ${THEME.glow2} 0%, transparent 72%)`,
          right: -180 + Math.cos(frame / 80) * 90,
          bottom: -260 + Math.sin(frame / 70) * 60,
          filter: "blur(34px)",
        }}
      />
      <div
        style={{
          position: "absolute",
          width: 820,
          height: 820,
          borderRadius: "50%",
          background: `radial-gradient(circle, ${THEME.glow3} 0%, transparent 70%)`,
          left: Math.round(WIDTH * 0.3) + Math.sin(frame / 60) * 110,
          top: Math.round(HEIGHT * 0.18) + Math.cos(frame / 65) * 80,
          filter: "blur(30px)",
        }}
      />

      {/* Subtle 3D ceiling perspective grid */}
      <div
        style={{
          position: "absolute",
          left: -400,
          right: -400,
          top: -170,
          height: 440,
          perspective: 720,
          overflow: "hidden",
          opacity: 0.2,
        }}
      >
        <div
          style={{
            width: "100%",
            height: "180%",
            transform: "rotateX(-70deg)",
            transformOrigin: "center top",
            backgroundImage: `linear-gradient(${THEME.grid1} 1px, transparent 1px), linear-gradient(90deg, ${THEME.grid2} 1px, transparent 1px)`,
            backgroundSize: "80px 80px",
            backgroundPosition: `0px ${-gridShift}px`,
          }}
        />
      </div>

      {/* 3D floor perspective grid */}
      <div
        style={{
          position: "absolute",
          left: -400,
          right: -400,
          bottom: -140,
          height: 620,
          perspective: 700,
          overflow: "hidden",
          opacity: 0.48,
        }}
      >
        <div
          style={{
            width: "100%",
            height: "180%",
            transform: "rotateX(70deg)",
            transformOrigin: "center bottom",
            backgroundImage: `linear-gradient(${THEME.grid1} 1px, transparent 1px), linear-gradient(90deg, ${THEME.grid2} 1px, transparent 1px)`,
            backgroundSize: "80px 80px",
            backgroundPosition: `0px ${gridShift}px`,
          }}
        />
      </div>

      {/* 3D orbital radar rings tilted in deep background */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          perspective: 1100,
          pointerEvents: "none",
          opacity: 0.28,
        }}
      >
        <div
          style={{
            width: IS_PORTRAIT ? 760 : 1080,
            height: IS_PORTRAIT ? 760 : 1080,
            position: "relative",
            transformStyle: "preserve-3d",
            transform: `rotateX(64deg) rotateY(${Math.sin(frame / 90) * 10}deg) rotateZ(${frame * 0.18}deg)`,
          }}
        >
          {[1.0, 0.74, 0.48].map((scale, idx) => (
            <div
              key={idx}
              style={{
                position: "absolute",
                inset: `${(1 - scale) * 50}%`,
                borderRadius: "50%",
                border: `${idx === 0 ? 2 : 1.5}px ${idx === 1 ? "dashed" : "solid"} ${[CYAN, BLUE, VIOLET][idx]}`,
                boxShadow: `0 0 24px ${[CYAN, BLUE, VIOLET][idx]}55`,
              }}
            />
          ))}
          <div
            style={{
              position: "absolute",
              inset: 0,
              borderRadius: "50%",
              background: `conic-gradient(from ${radarAngle}deg, ${CYAN}44 0deg, transparent 58deg, transparent 360deg)`,
            }}
          />
        </div>
      </div>

      {/* Floating 3D wireframe shards with parallax */}
      {HEX_SHARDS.map((h, idx) => {
        const rot = frame * h.speed * (idx % 2 === 0 ? 1 : -1);
        const yOff = Math.sin((frame + idx * 35) / 40) * 16;
        return (
          <div
            key={`shard-${idx}`}
            style={{
              position: "absolute",
              left: h.x,
              top: h.y + yOff,
              width: h.size,
              height: h.size,
              perspective: 500,
              opacity: 0.22,
              pointerEvents: "none",
            }}
          >
            <div
              style={{
                width: "100%",
                height: "100%",
                border: `1.5px solid ${h.color}`,
                borderRadius: idx % 2 === 0 ? 10 : 4,
                transform: `rotateX(${45 + rot * 0.6}deg) rotateY(${rot}deg) rotateZ(45deg)`,
                boxShadow: `0 0 18px ${h.color}55`,
              }}
            />
          </div>
        );
      })}

      {/* Flowing 3D background code columns from the real project (optional, low opacity for legibility) */}
      {(DECK.bg_code_streams ?? []).slice(0, 2).map((lines, colIdx) => {
        const isLeft = colIdx === 0;
        const doubled = [...lines, "", ...lines];
        const lineH = 26;
        const cycleH = Math.max(1, (lines.length + 1) * lineH);
        const scrollY = (frame * (isLeft ? 0.65 : 0.52)) % cycleH;
        return (
          <div
            key={`bg-code-${colIdx}`}
            style={{
              position: "absolute",
              top: 60,
              bottom: 60,
              left: isLeft ? 28 : undefined,
              right: isLeft ? undefined : 28,
              width: IS_PORTRAIT ? 340 : 540,
              perspective: 1100,
              overflow: "hidden",
              pointerEvents: "none",
              maskImage: "linear-gradient(180deg, transparent 0%, black 18%, black 82%, transparent 100%)",
              WebkitMaskImage: "linear-gradient(180deg, transparent 0%, black 18%, black 82%, transparent 100%)",
            }}
          >
            <div
              style={{
                transform: `rotateY(${isLeft ? 22 : -22}deg) rotateX(6deg) translateY(${-scrollY}px)`,
                transformOrigin: isLeft ? "left center" : "right center",
                fontFamily: "Consolas, 'Cascadia Code', monospace",
                fontSize: 15,
                lineHeight: `${lineH}px`,
                color: isLeft ? CYAN : BLUE,
                opacity: 0.16,
                whiteSpace: "pre",
                textShadow: `0 0 12px ${isLeft ? CYAN : BLUE}55`,
              }}
            >
              {doubled.join("\n")}
            </div>
          </div>
        );
      })}

      {/* Connected constellation mesh + glowing particles */}
      <svg width={WIDTH} height={HEIGHT} style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
        {meshLinks.map((l, idx) => (
          <line
            key={idx}
            x1={l.x1}
            y1={l.y1}
            x2={l.x2}
            y2={l.y2}
            stroke={l.color}
            strokeWidth={1.2}
            strokeOpacity={l.op}
          />
        ))}
      </svg>
      {liveParticles.map((p, idx) => (
        <div
          key={idx}
          style={{
            position: "absolute",
            left: p.px,
            top: p.py,
            width: p.r * 2,
            height: p.r * 2,
            borderRadius: "50%",
            backgroundColor: p.color,
            opacity: 0.58,
            boxShadow: `0 0 14px ${p.color}`,
          }}
        />
      ))}

      {/* Subtle radial vignette so foreground content pops */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: "radial-gradient(circle at center, transparent 52%, rgba(2,6,18,0.52) 100%)",
          pointerEvents: "none",
        }}
      />
    </AbsoluteFill>
  );
};

const Cube3D: React.FC<{ size?: number; faces?: string[] }> = ({
  size = 210,
  faces = ["DUP", "L1", "RUST", "SPOT", "MESH", "EVM"],
}) => {
  const frame = useCurrentFrame();
  const half = size / 2;
  const rx = 22 + Math.sin(frame / 38) * 16;
  const ry = frame * 1.45;
  const floatY = Math.sin(frame / 32) * 10;
  const f = (i: number) => faces[i % faces.length] ?? "";
  const stageSize = Math.round(size * 1.95);

  const faceBase: React.CSSProperties = {
    position: "absolute",
    width: size,
    height: size,
    border: `2px solid ${CYAN}`,
    background: `linear-gradient(135deg, ${THEME.glow1}, ${THEME.glow3}, ${THEME.glow2})`,
    boxShadow: `inset 0 0 32px ${THEME.glow3}, 0 0 28px ${THEME.glow1}`,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: Math.round(size * 0.13),
    fontWeight: 800,
    color: TEXT,
    letterSpacing: 3,
    backfaceVisibility: "visible",
    borderRadius: 12,
  };

  const ringBase: React.CSSProperties = {
    position: "absolute",
    left: "50%",
    top: "50%",
    borderRadius: "50%",
    transformStyle: "preserve-3d",
    pointerEvents: "none",
  };

  return (
    <div
      style={{
        width: stageSize,
        height: stageSize,
        perspective: 1100,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        position: "relative",
      }}
    >
      {/* Holographic projection floor ring */}
      <div
        style={{
          position: "absolute",
          bottom: 12,
          width: size * 1.35,
          height: size * 1.35,
          borderRadius: "50%",
          transform: "rotateX(78deg)",
          background: `radial-gradient(circle, ${CYAN}55 0%, ${BLUE}22 45%, transparent 72%)`,
          border: `1.5px solid ${CYAN}88`,
          boxShadow: `0 0 40px ${CYAN}44`,
        }}
      />

      {/* Multi-axis 3D gyroscopic orbital rings + inner cube */}
      <div
        style={{
          width: stageSize,
          height: stageSize,
          position: "relative",
          transformStyle: "preserve-3d",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          transform: `translateY(${floatY}px)`,
        }}
      >
        {/* Outer gyro ring */}
        <div
          style={{
            ...ringBase,
            width: size * 1.72,
            height: size * 1.72,
            marginLeft: -(size * 1.72) / 2,
            marginTop: -(size * 1.72) / 2,
            border: `2px solid ${CYAN}99`,
            boxShadow: `0 0 22px ${CYAN}55`,
            transform: `rotateX(68deg) rotateY(${frame * 0.7}deg) rotateZ(${frame * 1.2}deg)`,
          }}
        >
          <div style={{ position: "absolute", top: -6, left: "50%", width: 12, height: 12, borderRadius: "50%", background: CYAN, boxShadow: `0 0 18px ${CYAN}` }} />
        </div>

        {/* Middle gyro ring */}
        <div
          style={{
            ...ringBase,
            width: size * 1.48,
            height: size * 1.48,
            marginLeft: -(size * 1.48) / 2,
            marginTop: -(size * 1.48) / 2,
            border: `2px dashed ${VIOLET}aa`,
            boxShadow: `0 0 20px ${VIOLET}44`,
            transform: `rotateX(${-54 + Math.sin(frame / 45) * 14}deg) rotateY(${-frame * 1.1}deg) rotateZ(${frame * 0.9}deg)`,
          }}
        >
          <div style={{ position: "absolute", right: -6, top: "50%", width: 11, height: 11, borderRadius: "50%", background: PINK, boxShadow: `0 0 18px ${PINK}` }} />
        </div>

        {/* Inner vertical gyro ring */}
        <div
          style={{
            ...ringBase,
            width: size * 1.28,
            height: size * 1.28,
            marginLeft: -(size * 1.28) / 2,
            marginTop: -(size * 1.28) / 2,
            border: `1.5px solid ${BLUE}aa`,
            transform: `rotateY(${frame * 1.6}deg) rotateX(28deg)`,
          }}
        />

        {/* Core 3D glass cube */}
        <div style={{ width: size, height: size, position: "relative", transformStyle: "preserve-3d", transform: `rotateX(${rx}deg) rotateY(${ry}deg)` }}>
          {/* Pulsing inner energy core */}
          <div
            style={{
              position: "absolute",
              left: "50%",
              top: "50%",
              width: size * 0.42,
              height: size * 0.42,
              marginLeft: -(size * 0.42) / 2,
              marginTop: -(size * 0.42) / 2,
              borderRadius: "50%",
              background: `radial-gradient(circle, ${CYAN} 0%, ${VIOLET} 65%, transparent 100%)`,
              boxShadow: `0 0 42px ${CYAN}`,
              opacity: 0.7 + Math.sin(frame / 14) * 0.22,
            }}
          />
          <div style={{ ...faceBase, transform: `translateZ(${half}px)` }}>{f(0)}</div>
          <div style={{ ...faceBase, transform: `rotateY(180deg) translateZ(${half}px)` }}>{f(1)}</div>
          <div style={{ ...faceBase, transform: `rotateY(90deg) translateZ(${half}px)` }}>{f(2)}</div>
          <div style={{ ...faceBase, transform: `rotateY(-90deg) translateZ(${half}px)` }}>{f(3)}</div>
          <div style={{ ...faceBase, transform: `rotateX(90deg) translateZ(${half}px)` }}>{f(4)}</div>
          <div style={{ ...faceBase, transform: `rotateX(-90deg) translateZ(${half}px)` }}>{f(5)}</div>
        </div>
      </div>
    </div>
  );
};

const SlideChrome: React.FC<{
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

const BulletItem: React.FC<{ title: string; desc: string; delay: number; accent?: string }> = ({
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
        borderRadius: 16,
        background: THEME.cardBg,
        border: `1px solid ${THEME.cardBorder}`,
        boxShadow: "0 10px 30px rgba(0,0,0,0.22)",
      }}
    >
      <div style={{ width: 11, height: 11, marginTop: 9, borderRadius: "50%", backgroundColor: accent, boxShadow: `0 0 12px ${accent}`, flexShrink: 0 }} />
      <div>
        <div style={{ fontSize: IS_PORTRAIT ? 24 : 25, fontWeight: 700, color: TEXT }}>{title}</div>
        <div style={{ fontSize: IS_PORTRAIT ? 19 : 19, color: MUTED, marginTop: 4, lineHeight: 1.35 }}>{desc}</div>
      </div>
    </div>
  );
};

const CodeWindow3D: React.FC<{ filename: string; lines: { text: string; color?: string }[]; delay?: number }> = ({
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

const ScreenWindow3D: React.FC<{
  src: string;
  caption: string;
  focus?: ScreenFocus;
  maxHeight?: number;
  delay?: number;
}> = ({
  src,
  caption,
  focus,
  maxHeight = IS_PORTRAIT ? 640 : 610,
  delay = 10,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
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
            <Img src={staticFile(src)} style={{ width: "100%", height: "auto", display: "block", transform: `scale(${scale})`, transformOrigin: origin }} />
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

const Hero3DSlide: React.FC<{ slide: ResolvedSlide }> = ({ slide }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame, fps, config: { damping: 180 } });
  return (
    <div style={{ width: "100%", display: "flex", flexDirection: IS_PORTRAIT ? "column" : "row", alignItems: "center", gap: IS_PORTRAIT ? 56 : 70 }}>
      <div style={{ flex: 1.25, display: "flex", flexDirection: "column", gap: 24, width: "100%" }}>
        <div style={{ fontSize: IS_PORTRAIT ? 84 : 112, fontWeight: 900, lineHeight: 1.04, opacity: s, ...GRADIENT_TITLE }}>
          {slide.title}
        </div>
        {slide.subtitle && <div style={{ fontSize: IS_PORTRAIT ? 30 : 34, color: TEXT, lineHeight: 1.32 }}>{slide.subtitle}</div>}
        <div style={{ display: "flex", gap: 16, marginTop: 8, flexWrap: "wrap" }}>
          {(slide.pills ?? []).map((p, idx) => {
            const cs = spring({ frame: frame - (14 + idx * 7), fps, config: { damping: 180 } });
            return (
              <div key={p.name} style={{ opacity: cs, padding: "12px 22px", borderRadius: 14, background: THEME.cardBg, border: `1px solid ${p.color}`, color: p.color, fontSize: 21, fontWeight: 700 }}>
                {p.name}
              </div>
            );
          })}
        </div>
      </div>
      <div style={{ flex: 0.75, display: "flex", justifyContent: "center" }}>
        <Cube3D size={IS_PORTRAIT ? 200 : 230} faces={slide.cube_faces} />
      </div>
    </div>
  );
};

const CodeSplitSlide: React.FC<{ slide: ResolvedSlide }> = ({ slide }) => (
  <div style={{ width: "100%", display: "flex", flexDirection: IS_PORTRAIT ? "column" : "row", gap: IS_PORTRAIT ? 32 : 52, alignItems: "center" }}>
    <div style={{ flex: 0.95, display: "flex", flexDirection: "column", gap: 16, width: "100%" }}>
      <div style={{ fontSize: IS_PORTRAIT ? 52 : 58, fontWeight: 900, lineHeight: 1.08, ...GRADIENT_TITLE }}>{slide.title}</div>
      {slide.subtitle && <div style={{ fontSize: 24, color: MUTED, marginBottom: 4 }}>{slide.subtitle}</div>}
      {(slide.bullets ?? []).map((b, idx) => (
        <BulletItem key={b.title} title={b.title} desc={b.desc} delay={10 + idx * 10} accent={b.accent ?? [CYAN, BLUE, VIOLET][idx % 3]} />
      ))}
    </div>
    <div style={{ flex: 1.15, width: "100%" }}>
      {slide.code && <CodeWindow3D filename={slide.code.filename} lines={slide.code.lines} />}
    </div>
  </div>
);

/* Timeline: ordered steps from real facts (bullets), a line that draws itself and numbered nodes. */
const TimelineSlide: React.FC<{ slide: ResolvedSlide }> = ({ slide }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const steps = slide.bullets ?? [];
  const drawn = interpolate(frame, [8, 8 + Math.max(1, steps.length) * 12], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <div style={{ width: "100%", display: "flex", flexDirection: "column", gap: IS_PORTRAIT ? 28 : 22 }}>
      <div style={{ fontSize: IS_PORTRAIT ? 52 : 58, fontWeight: 900, lineHeight: 1.08, ...GRADIENT_TITLE }}>{slide.title}</div>
      {slide.subtitle && <div style={{ fontSize: 24, color: MUTED }}>{slide.subtitle}</div>}
      <div style={{ position: "relative", paddingLeft: 56, display: "flex", flexDirection: "column", gap: 20 }}>
        <div style={{ position: "absolute", left: 27, top: 18, bottom: 18, width: 4, borderRadius: 4, background: "rgba(255,255,255,0.10)" }}>
          <div
            style={{
              width: "100%",
              height: `${drawn * 100}%`,
              borderRadius: 4,
              background: `linear-gradient(180deg, ${CYAN}, ${BLUE}, ${VIOLET})`,
              boxShadow: `0 0 14px ${CYAN}`,
            }}
          />
        </div>
        {steps.map((b, i) => {
          const s = spring({ frame: frame - (12 + i * 12), fps, config: { damping: 180 } });
          const accent = b.accent ?? [CYAN, BLUE, VIOLET][i % 3];
          return (
            <div
              key={b.title}
              style={{
                position: "relative",
                opacity: s,
                transform: `translateX(${(1 - s) * 36}px)`,
                background: THEME.cardBg,
                border: `1px solid ${THEME.cardBorder}`,
                borderRadius: 16,
                padding: IS_PORTRAIT ? "14px 18px" : "16px 24px",
              }}
            >
              <div
                style={{
                  position: "absolute",
                  left: -46,
                  top: 18,
                  width: 38,
                  height: 38,
                  borderRadius: "50%",
                  background: accent,
                  color: THEME.bg,
                  fontWeight: 900,
                  fontSize: 16,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  boxShadow: `0 0 16px ${accent}`,
                }}
              >
                {String(i + 1).padStart(2, "0")}
              </div>
              <div style={{ fontSize: IS_PORTRAIT ? 28 : 30, fontWeight: 800, color: accent }}>{b.title}</div>
              <div style={{ fontSize: IS_PORTRAIT ? 22 : 24, color: TEXT, marginTop: 6, lineHeight: 1.35 }}>{b.desc}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

/* KPI: 1-4 big numbers copied verbatim from facts; each card springs in with its label. */
const KpiSlide: React.FC<{ slide: ResolvedSlide }> = ({ slide }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const kpis = slide.kpis ?? [];
  const cols = IS_PORTRAIT ? 1 : Math.min(Math.max(kpis.length, 1), 2);
  return (
    <div style={{ width: "100%", display: "flex", flexDirection: "column", gap: IS_PORTRAIT ? 28 : 22 }}>
      <div style={{ fontSize: IS_PORTRAIT ? 52 : 58, fontWeight: 900, lineHeight: 1.08, ...GRADIENT_TITLE }}>{slide.title}</div>
      {slide.subtitle && <div style={{ fontSize: 24, color: MUTED }}>{slide.subtitle}</div>}
      <div style={{ display: "grid", gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: 24, marginTop: 8 }}>
        {kpis.map((k, i) => {
          const s = spring({ frame: frame - (10 + i * 10), fps, config: { damping: 180 } });
          const accent = [CYAN, BLUE, VIOLET][i % 3];
          return (
            <div
              key={`${k.value}-${i}`}
              style={{
                opacity: s,
                transform: `scale(${0.9 + 0.1 * s})`,
                background: THEME.cardBg,
                border: `1px solid ${THEME.cardBorder}`,
                borderRadius: 20,
                padding: IS_PORTRAIT ? "20px 22px" : "26px 30px",
                boxShadow: `0 0 24px ${accent}33`,
              }}
            >
              <div style={{ fontSize: IS_PORTRAIT ? 64 : 80, fontWeight: 900, lineHeight: 1, color: accent, textShadow: `0 0 18px ${accent}` }}>
                {k.value}
              </div>
              <div style={{ fontSize: IS_PORTRAIT ? 24 : 26, color: TEXT, marginTop: 12, lineHeight: 1.3 }}>{k.label}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

/* Terminal: the real code excerpt is typed out character by character, with a blinking cursor. */
const TerminalWindow: React.FC<{ filename: string; lines: { text: string; color?: string }[] }> = ({ filename, lines }) => {
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

const TerminalSlide: React.FC<{ slide: ResolvedSlide }> = ({ slide }) => (
  <div style={{ width: "100%", display: "flex", flexDirection: IS_PORTRAIT ? "column" : "row", gap: IS_PORTRAIT ? 32 : 52, alignItems: "center" }}>
    <div style={{ flex: 0.95, display: "flex", flexDirection: "column", gap: 16, width: "100%" }}>
      <div style={{ fontSize: IS_PORTRAIT ? 52 : 58, fontWeight: 900, lineHeight: 1.08, ...GRADIENT_TITLE }}>{slide.title}</div>
      {slide.subtitle && <div style={{ fontSize: 24, color: MUTED, marginBottom: 4 }}>{slide.subtitle}</div>}
      {(slide.bullets ?? []).map((b, idx) => (
        <BulletItem key={b.title} title={b.title} desc={b.desc} delay={10 + idx * 10} accent={b.accent ?? [CYAN, BLUE, VIOLET][idx % 3]} />
      ))}
    </div>
    <div style={{ flex: 1.15, width: "100%" }}>
      {slide.code && <TerminalWindow filename={slide.code.filename} lines={slide.code.lines} />}
    </div>
  </div>
);

const ScreenSplitSlide: React.FC<{ slide: ResolvedSlide; dur: number }> = ({ slide, dur }) => {
  const frame = useCurrentFrame();
  const screens = slide.screens ?? [];
  const sliceLen = Math.max(1, Math.floor(dur / Math.max(1, screens.length)));
  const activeIdx = Math.min(screens.length - 1, Math.floor(frame / sliceLen));
  const active = screens[activeIdx];

  return (
    <div style={{ width: "100%", display: "flex", flexDirection: IS_PORTRAIT ? "column" : "row", gap: IS_PORTRAIT ? 32 : 48, alignItems: "center" }}>
      <div style={{ flex: 0.88, display: "flex", flexDirection: "column", gap: 16, width: "100%" }}>
        <div style={{ fontSize: IS_PORTRAIT ? 48 : 54, fontWeight: 900, lineHeight: 1.08, ...GRADIENT_TITLE }}>{slide.title}</div>
        {slide.subtitle && <div style={{ fontSize: 23, color: MUTED, marginBottom: 4 }}>{slide.subtitle}</div>}
        {(slide.bullets ?? []).map((b, idx) => (
          <BulletItem key={b.title} title={b.title} desc={b.desc} delay={10 + idx * 10} accent={b.accent ?? [CYAN, BLUE, VIOLET][idx % 3]} />
        ))}
      </div>
      <div style={{ flex: 1.32, width: "100%" }}>
        {active && <ScreenWindow3D key={active.src} src={active.src} caption={active.caption} focus={active.focus} delay={activeIdx === 0 ? 8 : 0} />}
      </div>
    </div>
  );
};

const ArchFlowSlide: React.FC<{ slide: ResolvedSlide }> = ({ slide }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const nodes = slide.arch?.nodes ?? [];
  const edges = slide.arch?.edges ?? [];
  const accents = [CYAN, BLUE, VIOLET, PINK, CYAN];

  // Sequential active spotlight sweeping across modules so the mechanism feels alive
  const activeStep = nodes.length > 0 ? Math.floor(frame / 42) % nodes.length : 0;

  if (IS_PORTRAIT) {
    return (
      <div style={{ width: "100%", display: "flex", flexDirection: "column", gap: 22 }}>
        <div>
          <div style={{ fontSize: 52, fontWeight: 900, lineHeight: 1.08, ...GRADIENT_TITLE }}>{slide.title}</div>
          {slide.subtitle && <div style={{ fontSize: 24, color: MUTED, marginTop: 6 }}>{slide.subtitle}</div>}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          {nodes.map((node, idx) => {
            const s = spring({ frame: frame - (8 + idx * 8), fps, config: { damping: 170 } });
            const color = accents[idx % accents.length];
            const isActive = idx === activeStep;
            return (
              <div
                key={node.id}
                style={{
                  opacity: s,
                  transform: `translateY(${interpolate(s, [0, 1], [20, 0])}px)`,
                  padding: "18px 20px",
                  borderRadius: 18,
                  background: THEME.cardBg,
                  border: `2px solid ${color}`,
                  boxShadow: isActive ? `0 0 32px ${color}66` : `0 12px 30px rgba(0,0,0,0.32)`,
                }}
              >
                <div style={{ fontSize: 13, fontFamily: "Consolas, monospace", color, fontWeight: 700, letterSpacing: 1.5 }}>
                  {String(idx + 1).padStart(2, "0")} · MODULE
                </div>
                <div style={{ fontSize: 25, fontWeight: 800, color: TEXT, marginTop: 4 }}>{node.label}</div>
                {node.path && <div style={{ fontSize: 15, fontFamily: "Consolas, monospace", color: MUTED, marginTop: 6 }}>{node.path}</div>}
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  // Landscape 1920x1080: 3D tilted architectural schematic with exact SVG conduits + animated data packets
  const stageW = 1720;
  const stageH = 560;
  const cardW = 420;
  const cardH = 176;
  const topCount = Math.min(3, nodes.length);
  const botCount = Math.max(0, nodes.length - topCount);

  const posMap: Record<string, { x: number; y: number; cx: number; cy: number; idx: number }> = {};
  nodes.forEach((node, idx) => {
    const isTop = idx < topCount;
    const rowCount = isTop ? topCount : botCount;
    const col = isTop ? idx : idx - topCount;
    const gapX = rowCount > 1 ? Math.min(190, (stageW - rowCount * cardW) / (rowCount - 1)) : 0;
    const rowW = rowCount * cardW + Math.max(0, rowCount - 1) * gapX;
    const startX = (stageW - rowW) / 2;
    const x = startX + col * (cardW + gapX);
    const y = isTop ? 36 : 334;
    posMap[node.id] = { x, y, cx: x + cardW / 2, cy: y + cardH / 2, idx };
  });

  const stageTiltX = 7 + Math.sin(frame / 58) * 1.8;
  const stageTiltY = -2.5 + Math.cos(frame / 66) * 1.8;

  return (
    <div style={{ width: "100%", display: "flex", flexDirection: "column", gap: 18 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
        <div>
          <div style={{ fontSize: 58, fontWeight: 900, lineHeight: 1.06, ...GRADIENT_TITLE }}>{slide.title}</div>
          {slide.subtitle && <div style={{ fontSize: 24, color: MUTED, marginTop: 6 }}>{slide.subtitle}</div>}
        </div>
        <div
          style={{
            padding: "8px 16px",
            borderRadius: 999,
            background: THEME.cardBg,
            border: `1px solid ${CYAN}77`,
            fontFamily: "Consolas, monospace",
            fontSize: 14,
            color: CYAN,
            letterSpacing: 1.5,
          }}
        >
          3D DATA PIPELINE · {nodes.length} LAYERS
        </div>
      </div>

      {/* 3D Perspective Architectural Stage */}
      <div style={{ width: "100%", display: "flex", justifyContent: "center", perspective: 1800 }}>
        <div
          style={{
            width: stageW,
            height: stageH,
            position: "relative",
            transformStyle: "preserve-3d",
            transform: `rotateX(${stageTiltX}deg) rotateY(${stageTiltY}deg)`,
          }}
        >
          {/* Architectural blueprint floor grid under the 3D modules */}
          <div
            style={{
              position: "absolute",
              inset: -10,
              borderRadius: 28,
              border: `1px solid ${CYAN}33`,
              background: `linear-gradient(135deg, rgba(10,18,38,0.58), rgba(14,24,52,0.34))`,
              backgroundImage: `linear-gradient(${CYAN}16 1px, transparent 1px), linear-gradient(90deg, ${BLUE}16 1px, transparent 1px)`,
              backgroundSize: "48px 48px",
              transform: "translateZ(-32px)",
              boxShadow: `inset 0 0 60px rgba(0,245,212,0.08), 0 36px 90px rgba(0,0,0,0.55)`,
            }}
          />

          {/* Animated SVG Data Conduits & Traveling Light Packets */}
          <svg
            width={stageW}
            height={stageH}
            style={{ position: "absolute", inset: 0, overflow: "visible", pointerEvents: "none" }}
          >
            <defs>
              <filter id="pipeGlow" x="-30%" y="-30%" width="160%" height="160%">
                <feGaussianBlur stdDeviation="4" result="blur" />
                <feMerge>
                  <feMergeNode in="blur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>
            {edges.map((e, idx) => {
              const p1 = posMap[e.from];
              const p2 = posMap[e.to];
              if (!p1 || !p2) return null;
              const edgeColor = accents[idx % accents.length];
              const sameRow = Math.abs(p1.y - p2.y) < 40;

              let sx: number;
              let sy: number;
              let ex: number;
              let ey: number;
              let mx: number;
              let my: number;
              let pathD: string;
              let samplePoint: (t: number) => { x: number; y: number };

              if (sameRow) {
                const leftToRight = p1.x < p2.x;
                sx = leftToRight ? p1.x + cardW : p1.x;
                sy = p1.cy;
                ex = leftToRight ? p2.x : p2.x + cardW;
                ey = p2.cy;
                mx = (sx + ex) / 2;
                my = sy;
                pathD = `M ${sx} ${sy} L ${ex} ${ey}`;
                samplePoint = (t) => ({ x: sx + (ex - sx) * t, y: sy + (ey - sy) * t });
              } else {
                // Smooth S-curve data bus dropping from top row to bottom row
                sx = p1.cx;
                sy = p1.y + cardH;
                ex = p2.cx;
                ey = p2.y;
                const midY = (sy + ey) / 2;
                mx = (sx + ex) / 2;
                my = midY;
                pathD = `M ${sx} ${sy} C ${sx} ${midY}, ${ex} ${midY}, ${ex} ${ey}`;
                samplePoint = (t) => {
                  const u = 1 - t;
                  const x = u * u * u * sx + 3 * u * u * t * sx + 3 * u * t * t * ex + t * t * t * ex;
                  const y = u * u * u * sy + 3 * u * u * t * midY + 3 * u * t * t * midY + t * t * t * ey;
                  return { x, y };
                };
              }

              const edgeAlpha = interpolate(frame, [20 + idx * 8, 34 + idx * 8], [0, 1], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              });
              const t1 = ((frame * 0.018 + idx * 0.27) % 1 + 1) % 1;
              const t2 = ((t1 + 0.5) % 1 + 1) % 1;
              const pt1 = samplePoint(t1);
              const pt2 = samplePoint(t2);

              return (
                <g key={`${e.from}-${e.to}-${idx}`} opacity={edgeAlpha}>
                  {/* Outer conduit glow */}
                  <path d={pathD} fill="none" stroke={edgeColor} strokeWidth={6} strokeOpacity={0.22} />
                  {/* Animated dashed inner data lane */}
                  <path
                    d={pathD}
                    fill="none"
                    stroke={edgeColor}
                    strokeWidth={2.5}
                    strokeDasharray="10 8"
                    strokeDashoffset={-frame * 1.8}
                    filter="url(#pipeGlow)"
                  />
                  {/* Traveling data packets */}
                  <circle cx={pt1.x} cy={pt1.y} r={6.5} fill="#ffffff" stroke={edgeColor} strokeWidth={3} filter="url(#pipeGlow)" />
                  <circle cx={pt2.x} cy={pt2.y} r={4.5} fill={edgeColor} opacity={0.85} />
                  {/* Edge label pill on the pipe */}
                  {e.label && (
                    <g transform={`translate(${mx}, ${sameRow ? my - 26 : my})`}>
                      <rect x={-76} y={-15} width={152} height={30} rx={15} fill={THEME.bg} stroke={edgeColor} strokeWidth={1.5} />
                      <text
                        x={0}
                        y={5}
                        textAnchor="middle"
                        fill={TEXT}
                        fontSize={14}
                        fontWeight={700}
                        fontFamily="Consolas, monospace"
                      >
                        {e.label}
                      </text>
                    </g>
                  )}
                </g>
              );
            })}
          </svg>

          {/* 3D Extruded Architectural Module Blocks */}
          {nodes.map((node, idx) => {
            const p = posMap[node.id];
            if (!p) return null;
            const s = spring({ frame: frame - (8 + idx * 7), fps, config: { damping: 165 } });
            const color = accents[idx % accents.length];
            const isActive = idx === activeStep;
            const hoverZ = isActive ? 18 : 6;
            const pulse = 0.6 + Math.sin(frame / 10 + idx) * 0.4;

            return (
              <div
                key={node.id}
                style={{
                  position: "absolute",
                  left: p.x,
                  top: p.y,
                  width: cardW,
                  height: cardH,
                  opacity: s,
                  transformStyle: "preserve-3d",
                  transform: `translateZ(${hoverZ}px) translateY(${interpolate(s, [0, 1], [28, 0])}px)`,
                }}
              >
                {/* 3D extruded lower slab (physical thickness illusion) */}
                <div
                  style={{
                    position: "absolute",
                    inset: 0,
                    borderRadius: 20,
                    background: `linear-gradient(180deg, ${color}33, rgba(4,10,24,0.92))`,
                    border: `1.5px solid ${color}88`,
                    transform: "translateZ(-16px) translateY(10px) translateX(6px)",
                    boxShadow: isActive ? `0 20px 55px ${color}44` : "0 18px 40px rgba(0,0,0,0.5)",
                  }}
                />
                {/* Main top face of the 3D module */}
                <div
                  style={{
                    position: "relative",
                    width: "100%",
                    height: "100%",
                    padding: "20px 24px",
                    borderRadius: 20,
                    background: `linear-gradient(145deg, rgba(13,22,46,0.94), rgba(8,14,32,0.96))`,
                    border: `2px solid ${isActive ? color : `${color}aa`}`,
                    boxShadow: isActive
                      ? `inset 0 0 28px ${color}2e, 0 0 34px ${color}55`
                      : `inset 0 0 18px ${color}14, 0 12px 30px rgba(0,0,0,0.4)`,
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "space-between",
                    boxSizing: "border-box",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div style={{ fontSize: 13, fontFamily: "Consolas, monospace", color, fontWeight: 800, letterSpacing: 1.8 }}>
                      {String(idx + 1).padStart(2, "0")} · LAYER
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <div
                        style={{
                          width: 9,
                          height: 9,
                          borderRadius: "50%",
                          background: color,
                          opacity: isActive ? 1 : pulse * 0.55,
                          boxShadow: `0 0 ${isActive ? 16 : 8}px ${color}`,
                        }}
                      />
                      <span style={{ fontSize: 11, fontFamily: "Consolas, monospace", color: isActive ? color : MUTED, letterSpacing: 1.2 }}>
                        {isActive ? "ACTIVE" : "READY"}
                      </span>
                    </div>
                  </div>

                  <div style={{ fontSize: 28, fontWeight: 800, color: TEXT, lineHeight: 1.15 }}>{node.label}</div>

                  {node.path && (
                    <div
                      style={{
                        fontSize: 15,
                        fontFamily: "Consolas, monospace",
                        color: MUTED,
                        padding: "6px 10px",
                        borderRadius: 8,
                        background: "rgba(255,255,255,0.04)",
                        border: "1px solid rgba(255,255,255,0.08)",
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                      }}
                    >
                      {node.path}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

const Outro3DSlide: React.FC<{ slide: ResolvedSlide }> = ({ slide }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame, fps, config: { damping: 180 } });
  return (
    <div style={{ width: "100%", display: "flex", flexDirection: IS_PORTRAIT ? "column" : "row", alignItems: "center", justifyContent: "space-between", gap: IS_PORTRAIT ? 48 : 60, opacity: s }}>
      <div style={{ flex: 1.2, display: "flex", flexDirection: "column", gap: 22, width: "100%" }}>
        <div style={{ fontSize: IS_PORTRAIT ? 68 : 92, fontWeight: 900, lineHeight: 1.05, ...GRADIENT_TITLE }}>{slide.title}</div>
        {slide.url && <div style={{ fontSize: IS_PORTRAIT ? 34 : 46, fontWeight: 700, color: TEXT, wordBreak: "break-all" }}>{slide.url}</div>}
        <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginTop: 6 }}>
          {(slide.badges ?? []).map((repo) => (
            <div key={repo.name} style={{ padding: "11px 20px", borderRadius: 12, background: THEME.cardBg, border: `1px solid ${repo.color}`, color: repo.color, fontSize: 22, fontFamily: "Consolas, monospace", fontWeight: 700 }}>
              {repo.name}
            </div>
          ))}
        </div>
        {slide.tagline && <div style={{ fontSize: 26, color: MUTED, marginTop: 8 }}>{slide.tagline}</div>}
      </div>
      <div style={{ flex: 0.7, display: "flex", justifyContent: "center" }}>
        <Cube3D size={IS_PORTRAIT ? 190 : 210} faces={slide.cube_faces} />
      </div>
    </div>
  );
};

const CaptionOverlay: React.FC<{ captions?: CaptionCue[] }> = ({ captions }) => {
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
          fontSize: IS_PORTRAIT ? 28 : 24,
          fontWeight: 600,
          lineHeight: 1.32,
          textAlign: "center",
          maxWidth: "100%",
          boxShadow: "0 12px 30px rgba(0,0,0,0.45)",
        }}
      >
        {active.speaker && (
          <span style={{ color: active.speaker === "B" ? PINK : CYAN, marginRight: 10, fontFamily: "Consolas, monospace" }}>
            [{active.speaker}]
          </span>
        )}
        {active.words && active.words.length > 0 ? (
          <span>
            {active.words.map((wd, idx) => {
              const isCurrent = sec >= wd.start && sec <= wd.end;
              const isSpoken = sec > wd.end;
              return (
                <span
                  key={`${idx}-${wd.w}`}
                  style={{
                    display: "inline-block",
                    marginRight: 7,
                    padding: isCurrent ? "1px 7px" : "1px 1px",
                    borderRadius: 7,
                    background: isCurrent ? `${CYAN}2e` : "transparent",
                    color: isCurrent ? CYAN : isSpoken ? THEME.captionText : `${THEME.captionText}b8`,
                    textShadow: isCurrent ? `0 0 14px ${CYAN}88` : "none",
                    transform: isCurrent ? "scale(1.04)" : "scale(1)",
                  }}
                >
                  {wd.w}
                </span>
              );
            })}
          </span>
        ) : (
          active.text
        )}
      </div>
    </div>
  );
};

const ProgressBar: React.FC = () => {
  const frame = useCurrentFrame();
  const pct = (frame / Math.max(1, DURATION)) * 100;
  return (
    <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 7, background: "rgba(255,255,255,0.08)" }}>
      <div style={{ width: `${pct}%`, height: "100%", background: `linear-gradient(90deg, ${CYAN}, ${BLUE}, ${VIOLET}, ${PINK})`, boxShadow: `0 0 16px ${CYAN}` }} />
    </div>
  );
};

// Free stock clip behind a slide (Pexels / Pixabay). Dimmed by theme bg so text stays readable.
const StockBackdrop: React.FC<{ slide: ResolvedSlide; dur: number }> = ({ slide, dur }) => {
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

const renderSlideTransition = (idx: number, key: string) => {
  const timing = linearTiming({ durationInFrames: TRANSITION_FRAMES });
  if (TRANSITION_STYLE === "slide") {
    return (
      <TransitionSeries.Transition
        key={key}
        presentation={slideTransition({ direction: idx % 2 === 0 ? "from-right" : "from-bottom" })}
        timing={timing}
      />
    );
  }
  if (TRANSITION_STYLE === "wipe") {
    return <TransitionSeries.Transition key={key} presentation={wipe({ direction: "from-left" })} timing={timing} />;
  }
  return <TransitionSeries.Transition key={key} presentation={fade()} timing={timing} />;
};

export const DupPresenter: React.FC<Props> = () => {
  const showCaptions = DECK.burn_captions !== false;
  const sfxEnabled = DECK.sfx_enabled !== false;
  const sfxVolume = DECK.sfx_volume ?? 0.22;
  const duckRatio = DECK.music_duck_ratio ?? 0.36;

  // Transition SFX trigger frames on the master timeline
  const transitionSoundFrames: number[] = [];
  if (sfxEnabled && DECK.sfx_transition_file && TRANSITION_FRAMES > 0) {
    let cursor = 0;
    for (let i = 0; i < DECK.slides.length - 1; i++) {
      cursor += Math.max(1, Math.round(DECK.slides[i].duration_sec * FPS)) - TRANSITION_FRAMES;
      transitionSoundFrames.push(Math.max(0, cursor - 2));
    }
  }

  const renderSlideBody = (slide: ResolvedSlide, durationInFrames: number): React.ReactNode => {
    if (slide.type === "hero_3d") return <Hero3DSlide slide={slide} />;
    if (slide.type === "code_split") return <CodeSplitSlide slide={slide} />;
    if (slide.type === "screen_split") return <ScreenSplitSlide slide={slide} dur={durationInFrames} />;
    if (slide.type === "arch_flow") return <ArchFlowSlide slide={slide} />;
    if (slide.type === "outro_3d") return <Outro3DSlide slide={slide} />;
    if (slide.type === "timeline") return <TimelineSlide slide={slide} />;
    if (slide.type === "terminal") return <TerminalSlide slide={slide} />;
    if (slide.type === "kpi") return <KpiSlide slide={slide} />;
    return null;
  };

  const renderSlideContent = (slide: ResolvedSlide, durationInFrames: number, hasTransition: boolean) => {
    const voiceDelayFrames = Math.max(0, Math.round((slide.voice_delay_sec ?? 0) * FPS));
    const wantsPop =
      sfxEnabled &&
      Boolean(DECK.sfx_pop_file) &&
      (slide.type === "kpi" || slide.type === "terminal" || slide.type === "hero_3d");
    return (
      <>
        <StockBackdrop slide={slide} dur={durationInFrames} />
        <SlideChrome
          brand={DECK.brand}
          num={slide.num}
          tag={slide.tag}
          dur={durationInFrames}
          hasTransition={hasTransition}
        >
          {renderSlideBody(slide, durationInFrames)}
        </SlideChrome>
        {showCaptions && <CaptionOverlay captions={slide.captions} />}
        <Sequence from={voiceDelayFrames}>
          <Audio src={staticFile(slide.voice_file)} startFrom={0} />
        </Sequence>
        {wantsPop && DECK.sfx_pop_file && (
          <Sequence from={Math.min(8, Math.max(0, durationInFrames - 6))} durationInFrames={15}>
            <Audio src={staticFile(DECK.sfx_pop_file)} volume={sfxVolume * 0.7} />
          </Sequence>
        )}
      </>
    );
  };

  return (
    <AbsoluteFill style={{ backgroundColor: BG }}>
      <Aurora3DBackdrop />
      <Audio
        src={staticFile(DECK.ambient_file)}
        volume={(f) => (DECK.voice?.ambient_volume ?? 0.16) * computeDuckFactor(f, Math.max(0.55, duckRatio))}
      />
      {DECK.music_file && (
        <Audio
          src={staticFile(DECK.music_file)}
          volume={(f) => {
            const v = DECK.music_volume ?? 0.12;
            const fadeLen = Math.min(2 * FPS, Math.floor(DURATION / 3));
            const env =
              fadeLen > 0
                ? interpolate(f, [0, fadeLen, DURATION - fadeLen, DURATION], [0, v, v, 0], {
                    extrapolateLeft: "clamp",
                    extrapolateRight: "clamp",
                  })
                : v;
            return env * computeDuckFactor(f, duckRatio);
          }}
        />
      )}
      {transitionSoundFrames.map((tf, idx) => (
        <Sequence key={`sfx-tr-${idx}`} from={tf} durationInFrames={Math.max(12, TRANSITION_FRAMES + 6)}>
          <Audio src={staticFile(DECK.sfx_transition_file!)} volume={sfxVolume} />
        </Sequence>
      ))}
      {TRANSITION_FRAMES > 0 ? (
        <TransitionSeries>
          {DECK.slides.map((slide, idx) => {
            const durationInFrames = Math.max(TRANSITION_FRAMES * 2 + 1, Math.round(slide.duration_sec * FPS));
            return (
              <React.Fragment key={slide.id}>
                <TransitionSeries.Sequence durationInFrames={durationInFrames}>
                  {renderSlideContent(slide, durationInFrames, true)}
                </TransitionSeries.Sequence>
                {idx < DECK.slides.length - 1 && renderSlideTransition(idx, `tr-${slide.id}`)}
              </React.Fragment>
            );
          })}
        </TransitionSeries>
      ) : (
        (() => {
          let offset = 0;
          return DECK.slides.map((slide) => {
            const from = offset;
            const durationInFrames = Math.max(1, Math.round(slide.duration_sec * FPS));
            offset += durationInFrames;
            return (
              <Sequence key={slide.id} from={from} durationInFrames={durationInFrames}>
                {renderSlideContent(slide, durationInFrames, false)}
              </Sequence>
            );
          });
        })()
      )}
      <ProgressBar />
    </AbsoluteFill>
  );
};

export const DupPresenterComposition = () => (
  <Composition
    id="DupPresenter"
    component={DupPresenter}
    durationInFrames={DURATION}
    fps={FPS}
    width={WIDTH}
    height={HEIGHT}
    calculateMetadata={calculateMetadata}
  />
);
