import React from "react";
import {
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { ResolvedSlide } from "../types";
import { Cube3D } from "./aurora3d";
import { CryptoMiniChart } from "./cosmicBackdrop";
import { BLUE, CYAN, IS_COSMIC, IS_LIGHT, IS_PORTRAIT, IS_QUANTUM, MUTED, PINK, TEXT, THEME, VIOLET } from "./deckContext";
import { AnimatedKpiValue, BulletItem, CodeWindow3D, EmbossedTitle, ScreenWindow3D, TerminalWindow } from "./primitives";

export const Hero3DSlide: React.FC<{ slide: ResolvedSlide }> = ({ slide }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame, fps, config: { damping: 180 } });
  return (
    <div style={{ width: "100%", display: "flex", flexDirection: IS_PORTRAIT ? "column" : "row", alignItems: "center", gap: IS_PORTRAIT ? 56 : 70 }}>
      <div style={{ flex: 1.25, display: "flex", flexDirection: "column", gap: 24, width: "100%" }}>
        <EmbossedTitle fontSize={IS_PORTRAIT ? 84 : 112} lineHeight={1.04} opacity={s}>
          {slide.title}
        </EmbossedTitle>
        {slide.subtitle && (
          <div style={{ fontSize: IS_PORTRAIT ? 30 : 34, color: TEXT, lineHeight: 1.32, textShadow: IS_LIGHT ? "none" : "0 2px 14px rgba(0,0,0,0.85)" }}>
            {slide.subtitle}
          </div>
        )}
        <div style={{ display: "flex", gap: 16, marginTop: 8, flexWrap: "wrap" }}>
          {(slide.pills ?? []).map((p, idx) => {
            const cs = spring({ frame: frame - (14 + idx * 7), fps, config: { damping: 180 } });
            return (
              <div
                key={p.name}
                style={{
                  opacity: cs,
                  padding: "12px 22px",
                  borderRadius: 14,
                  background: THEME.cardBg,
                  border: `1.5px solid ${p.color}`,
                  boxShadow: IS_LIGHT ? "none" : `0 10px 26px rgba(0,0,0,0.5), 0 0 18px ${p.color}33`,
                  color: p.color,
                  fontSize: 21,
                  fontWeight: 800,
                }}
              >
                {p.name}
              </div>
            );
          })}
        </div>
        {IS_COSMIC && (
          <div
            style={{
              marginTop: 12,
              padding: "14px 20px",
              borderRadius: 16,
              background: "rgba(5, 12, 30, 0.80)",
              border: `1px solid ${CYAN}44`,
              boxShadow: `0 16px 36px rgba(0,0,0,0.55), 0 0 24px ${CYAN}22`,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 20,
              maxWidth: IS_PORTRAIT ? "100%" : 660,
            }}
          >
            <div>
              <div style={{ fontSize: 12, fontFamily: "Consolas, monospace", letterSpacing: 1.8, color: CYAN, fontWeight: 700 }}>
                LIVE MARKET PULSE · SPOT SCANNER
              </div>
              <div style={{ fontSize: 20, fontWeight: 800, color: TEXT, marginTop: 4 }}>
                BTC · ETH · SOL · HYPE · BNB
              </div>
            </div>
            <CryptoMiniChart seed={7} accent={CYAN} width={220} height={54} bars={16} />
          </div>
        )}
      </div>
      <div style={{ flex: 0.75, display: "flex", justifyContent: "center" }}>
        <Cube3D size={IS_PORTRAIT ? 200 : 230} faces={slide.cube_faces} />
      </div>
    </div>
  );
};

export const CodeSplitSlide: React.FC<{ slide: ResolvedSlide }> = ({ slide }) => (
  <div style={{ width: "100%", display: "flex", flexDirection: IS_PORTRAIT ? "column" : "row", gap: IS_PORTRAIT ? 32 : 52, alignItems: "center" }}>
    <div style={{ flex: 0.95, display: "flex", flexDirection: "column", gap: 16, width: "100%" }}>
      <EmbossedTitle fontSize={IS_PORTRAIT ? 52 : 58} lineHeight={1.08}>{slide.title}</EmbossedTitle>
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

export const TimelineSlide: React.FC<{ slide: ResolvedSlide }> = ({ slide }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const steps = slide.bullets ?? [];
  const drawn = interpolate(frame, [8, 8 + Math.max(1, steps.length) * 12], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <div style={{ width: "100%", display: "flex", flexDirection: "column", gap: IS_PORTRAIT ? 28 : 22 }}>
      <EmbossedTitle fontSize={IS_PORTRAIT ? 52 : 58} lineHeight={1.08}>{slide.title}</EmbossedTitle>
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
/* Quote: one statement on screen with an attribution line. title = quote text, subtitle = author. */

export const QuoteSlide: React.FC<{ slide: ResolvedSlide }> = ({ slide }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - 8, fps, config: { damping: 200 } });
  const rule = interpolate(frame, [18, 48], [0, 100], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <div style={{ width: "100%", display: "flex", flexDirection: "column", gap: 24, opacity: s, transform: `translateY(${(1 - s) * 22}px)` }}>
      <div style={{ fontSize: IS_PORTRAIT ? 130 : 150, lineHeight: 0.6, color: CYAN, fontWeight: 900, fontFamily: "Georgia, serif", textShadow: `0 0 30px ${CYAN}88` }}>
        “
      </div>
      <div
        style={{
          maxWidth: IS_PORTRAIT ? "100%" : 1120,
          background: IS_QUANTUM
            ? `radial-gradient(ellipse at 50% -10%, rgba(255,255,255,0.20) 0%, transparent 52%), radial-gradient(ellipse at 50% 120%, ${CYAN}30 0%, transparent 60%), linear-gradient(155deg, rgba(10,22,56,0.94) 0%, rgba(4,10,28,0.96) 100%)`
            : THEME.cardBg,
          border: `2px solid ${CYAN}${IS_QUANTUM ? "bb" : "55"}`,
          borderTop: `2.5px solid ${CYAN}`,
          borderRadius: 24,
          padding: IS_PORTRAIT ? "22px 24px" : "30px 38px",
          boxShadow: IS_QUANTUM
            ? `0 10px 0 rgba(3,8,22,0.96), 0 14px 0 ${CYAN}55, 0 32px 68px rgba(0,0,0,0.82), 0 0 48px ${CYAN}40, inset 0 2px 4px rgba(255,255,255,0.30)`
            : "0 20px 48px rgba(0,0,0,0.6)",
          fontSize: IS_PORTRAIT ? 46 : 52,
          fontWeight: 900,
          lineHeight: 1.22,
          color: IS_QUANTUM ? "#ffffff" : TEXT,
          textShadow: IS_QUANTUM ? `0 2px 0 #051024, 0 5px 0 #020714, 0 14px 24px rgba(0,0,0,0.95), 0 0 24px ${CYAN}99` : undefined,
        }}
      >
        {slide.title}
      </div>
      <div style={{ height: 4, width: `${rule}%`, maxWidth: 360, background: `linear-gradient(90deg, ${CYAN}, ${VIOLET})`, borderRadius: 2 }} />
      {slide.subtitle && <div style={{ fontSize: 26, color: MUTED }}>{slide.subtitle}</div>}
    </div>
  );
};

export const KpiSlide: React.FC<{ slide: ResolvedSlide }> = ({ slide }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const kpis = slide.kpis ?? [];
  const cols = IS_PORTRAIT ? 1 : Math.min(Math.max(kpis.length, 1), 2);
  return (
    <div style={{ width: "100%", display: "flex", flexDirection: "column", gap: IS_PORTRAIT ? 28 : 22 }}>
      <EmbossedTitle fontSize={IS_PORTRAIT ? 52 : 58} lineHeight={1.08}>{slide.title}</EmbossedTitle>
      {slide.subtitle && <div style={{ fontSize: 24, color: MUTED }}>{slide.subtitle}</div>}
      <div style={{ display: "grid", gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: 26, marginTop: 10, perspective: 1700 }}>
        {kpis.map((k, i) => {
          const s = spring({ frame: frame - (10 + i * 10), fps, config: { damping: 180 } });
          const accent = [CYAN, BLUE, VIOLET, PINK][i % 4];
          const tiltY = IS_QUANTUM && !IS_PORTRAIT && cols === 2 ? (i % 2 === 0 ? 6 : -6) : 0;
          const numLiftShadow = IS_LIGHT
            ? `0 2px 0 rgba(15,23,42,0.18), 0 8px 18px rgba(15,23,42,0.16)`
            : IS_QUANTUM
            ? `0 2px 0 #0a1e40, 0 4px 0 #071630, 0 6px 0 #040d20, 0 8px 0 #020714, 0 20px 34px rgba(0,0,0,0.96), 0 0 34px ${accent}ee, 0 0 60px ${accent}66`
            : `0 1px 0 #0b2444, 0 2px 0 #091d38, 0 3px 0 #07162e, 0 4px 0 #050f22, 0 6px 0 #020814, 0 14px 28px rgba(0,0,0,0.88), 0 0 26px ${accent}cc, 0 0 48px ${accent}55`;
          return (
            <div
              key={`${k.value}-${i}`}
              style={{
                opacity: s,
                transform: `rotateY(${tiltY}deg) scale(${0.9 + 0.1 * s}) translateY(${(1 - s) * 18}px)`,
                transformStyle: "preserve-3d",
                background: IS_QUANTUM
                  ? `radial-gradient(ellipse at 50% -12%, rgba(255,255,255,0.22) 0%, transparent 52%), radial-gradient(ellipse at 50% 125%, ${accent}38 0%, transparent 60%), linear-gradient(155deg, ${accent}24 0%, rgba(7,16,42,0.94) 58%, rgba(3,8,24,0.96) 100%)`
                  : THEME.cardBg,
                border: `${IS_QUANTUM ? 2 : 1.5}px solid ${accent}${IS_QUANTUM ? "bb" : "55"}`,
                borderTop: `2.5px solid ${accent}`,
                borderRadius: 24,
                padding: IS_PORTRAIT ? "20px 22px" : "26px 30px",
                boxShadow: IS_LIGHT
                  ? `0 12px 28px rgba(15,23,42,0.10)`
                  : IS_QUANTUM
                  ? `0 10px 0 rgba(3,8,22,0.96), 0 14px 0 ${accent}55, 0 30px 64px rgba(0,0,0,0.82), 0 0 42px ${accent}44, inset 0 2px 4px rgba(255,255,255,0.32), inset 0 -8px 18px rgba(0,0,0,0.52)`
                  : `0 20px 48px rgba(0,0,0,0.62), 0 0 30px ${accent}28, inset 0 1px 0 rgba(255,255,255,0.12)`,
                display: "flex",
                flexDirection: "column",
                justifyContent: "space-between",
                gap: 12,
              }}
            >
              <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16, transformStyle: "preserve-3d" }}>
                <div
                  style={{
                    fontSize: IS_PORTRAIT ? 68 : 92,
                    fontWeight: 900,
                    lineHeight: 0.96,
                    letterSpacing: "-0.02em",
                    color: IS_LIGHT ? accent : "#ffffff",
                    textShadow: numLiftShadow,
                    transform: IS_QUANTUM ? "translateZ(30px) translateY(-6px)" : undefined,
                  }}
                >
                  <AnimatedKpiValue value={k.value} startFrame={10 + i * 10 + 6} />
                </div>
                <CryptoMiniChart seed={i + 2} accent={accent} width={IS_PORTRAIT ? 150 : 175} height={54} bars={12} />
              </div>
              <div style={{ fontSize: IS_PORTRAIT ? 24 : 25, fontWeight: 600, color: TEXT, lineHeight: 1.3 }}>{k.label}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

/* Terminal: the real code excerpt is typed out character by character, with a blinking cursor. */

export const TerminalSlide: React.FC<{ slide: ResolvedSlide }> = ({ slide }) => (
  <div style={{ width: "100%", display: "flex", flexDirection: IS_PORTRAIT ? "column" : "row", gap: IS_PORTRAIT ? 32 : 52, alignItems: "center" }}>
    <div style={{ flex: 0.95, display: "flex", flexDirection: "column", gap: 16, width: "100%" }}>
      <EmbossedTitle fontSize={IS_PORTRAIT ? 52 : 58} lineHeight={1.08}>{slide.title}</EmbossedTitle>
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

export const ScreenSplitSlide: React.FC<{ slide: ResolvedSlide; dur: number }> = ({ slide, dur }) => {
  const frame = useCurrentFrame();
  const screens = slide.screens ?? [];
  const sliceLen = Math.max(1, Math.floor(dur / Math.max(1, screens.length)));
  const activeIdx = Math.min(screens.length - 1, Math.floor(frame / sliceLen));
  const active = screens[activeIdx];

  return (
    <div style={{ width: "100%", display: "flex", flexDirection: IS_PORTRAIT ? "column" : "row", gap: IS_PORTRAIT ? 32 : 48, alignItems: "center" }}>
      <div style={{ flex: 0.88, display: "flex", flexDirection: "column", gap: 16, width: "100%" }}>
        <EmbossedTitle fontSize={IS_PORTRAIT ? 48 : 54} lineHeight={1.08}>{slide.title}</EmbossedTitle>
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

export const UiRecordingSlide: React.FC<{ slide: ResolvedSlide }> = ({ slide }) => {
  const rec = slide.recording;
  if (!rec) return null;
  return (
    <div style={{ width: "100%", display: "flex", flexDirection: IS_PORTRAIT ? "column" : "row", gap: IS_PORTRAIT ? 32 : 48, alignItems: "center" }}>
      <div style={{ flex: 0.88, display: "flex", flexDirection: "column", gap: 16, width: "100%" }}>
        <EmbossedTitle fontSize={IS_PORTRAIT ? 48 : 54} lineHeight={1.08}>{slide.title}</EmbossedTitle>
        {slide.subtitle && <div style={{ fontSize: 23, color: MUTED, marginBottom: 4 }}>{slide.subtitle}</div>}
        {(slide.bullets ?? []).map((b, idx) => (
          <BulletItem key={b.title} title={b.title} desc={b.desc} delay={10 + idx * 10} accent={b.accent ?? [CYAN, BLUE, VIOLET][idx % 3]} />
        ))}
      </div>
      <div style={{ flex: 1.32, width: "100%" }}>
        <ScreenWindow3D
          src={rec.src}
          caption={rec.caption ?? "UI recording"}
          focus={rec.focus}
          delay={8}
          isVideo
          videoDurationSec={rec.duration_sec ?? 0}
        />
      </div>
    </div>
  );
};

export const ArchFlowSlide: React.FC<{ slide: ResolvedSlide }> = ({ slide }) => {
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
          <EmbossedTitle fontSize={52} lineHeight={1.08}>{slide.title}</EmbossedTitle>
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
          <EmbossedTitle fontSize={58} lineHeight={1.06}>{slide.title}</EmbossedTitle>
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

export const Outro3DSlide: React.FC<{ slide: ResolvedSlide }> = ({ slide }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame, fps, config: { damping: 180 } });
  return (
    <div style={{ width: "100%", display: "flex", flexDirection: IS_PORTRAIT ? "column" : "row", alignItems: "center", justifyContent: "space-between", gap: IS_PORTRAIT ? 48 : 60, opacity: s }}>
      <div style={{ flex: 1.2, display: "flex", flexDirection: "column", gap: 22, width: "100%" }}>
        <EmbossedTitle fontSize={IS_PORTRAIT ? 68 : 92} lineHeight={1.05}>{slide.title}</EmbossedTitle>
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

// Burned-in subtitle presets (deck field caption_style). Timing base is slide-local, same as the cues.
