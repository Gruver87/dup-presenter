import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { ResolvedSlide } from "./types";
import type { ThemePalette } from "./themes";

interface StorySlideProps {
  slide: ResolvedSlide;
  dur: number;
  theme: ThemePalette;
  isPortrait: boolean;
}

/** Shared visual helpers for the inflated/beveled 3D shelves & floating detached typography. */
const floatTextShadow = (color: string, heavy = false): string =>
  heavy
    ? `0 2px 0 #071329, 0 4px 0 #040b1a, 0 6px 0 #020612, 0 16px 26px rgba(0,0,0,0.95), 0 0 26px ${color}cc`
    : `0 2px 0 #061024, 0 4px 0 #030916, 0 11px 18px rgba(0,0,0,0.90), 0 0 18px ${color}99`;

const inflatedCardBg = (color: string, active: boolean, baseBg: string, isQuantum: boolean): string => {
  if (!isQuantum) {
    return active ? `linear-gradient(135deg, ${color}26 0%, ${baseBg} 100%)` : baseBg;
  }
  return active
    ? `radial-gradient(ellipse at 50% -10%, rgba(255,255,255,0.22) 0%, transparent 52%), radial-gradient(ellipse at 50% 120%, ${color}38 0%, transparent 58%), linear-gradient(155deg, ${color}30 0%, rgba(7,16,42,0.94) 55%, rgba(3,8,24,0.96) 100%)`
    : `radial-gradient(ellipse at 50% -15%, rgba(255,255,255,0.12) 0%, transparent 48%), linear-gradient(160deg, rgba(14,26,62,0.88) 0%, rgba(5,11,30,0.92) 100%)`;
};

const inflatedCardShadow = (color: string, active: boolean, isQuantum: boolean): string => {
  if (!isQuantum) {
    return active ? `0 0 30px ${color}38, 0 14px 32px rgba(0,0,0,0.42)` : "0 10px 24px rgba(0,0,0,0.32)";
  }
  return active
    ? `0 7px 0 rgba(4,10,28,0.96), 0 11px 0 ${color}66, 0 26px 56px rgba(0,0,0,0.78), 0 0 42px ${color}55, inset 0 2px 3px rgba(255,255,255,0.32), inset 0 -8px 18px rgba(0,0,0,0.52)`
    : `0 6px 0 rgba(3,8,22,0.94), 0 18px 38px rgba(0,0,0,0.62), inset 0 1.5px 2px rgba(255,255,255,0.16), inset 0 -6px 14px rgba(0,0,0,0.44)`;
};

const StoryHeading: React.FC<{
  title: string;
  subtitle?: string;
  badge?: string;
  theme: ThemePalette;
  isPortrait: boolean;
}> = ({ title, subtitle, badge, theme, isPortrait }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const isQuantum = theme.id === "quantum_ledger";
  const s = spring({ frame, fps, config: { damping: 200 } });
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: isPortrait ? "flex-start" : "flex-end",
        flexDirection: isPortrait ? "column" : "row",
        gap: 12,
        opacity: s,
        transform: `translateY(${interpolate(s, [0, 1], [14, 0])}px)`,
      }}
    >
      <div>
        <div
          style={{
            fontSize: isPortrait ? 44 : 52,
            fontWeight: 900,
            lineHeight: 1.05,
            letterSpacing: -0.6,
            color: isQuantum ? "#ffffff" : undefined,
            background: isQuantum
              ? undefined
              : `linear-gradient(90deg, ${theme.text} 0%, ${theme.accent1} 65%, ${theme.accent3} 100%)`,
            WebkitBackgroundClip: isQuantum ? undefined : "text",
            WebkitTextFillColor: isQuantum ? undefined : "transparent",
            textShadow: isQuantum ? floatTextShadow(theme.accent1, true) : undefined,
          }}
        >
          {title}
        </div>
        {subtitle && (
          <div style={{ fontSize: isPortrait ? 20 : 22, color: theme.muted, marginTop: 7, lineHeight: 1.3 }}>
            {subtitle}
          </div>
        )}
      </div>
      {badge && (
        <div
          style={{
            padding: "9px 18px",
            borderRadius: 999,
            background: isQuantum
              ? `radial-gradient(ellipse at 50% 0%, rgba(255,255,255,0.18), transparent 60%), rgba(8,18,46,0.92)`
              : theme.cardBg,
            border: `1.5px solid ${theme.accent1}99`,
            fontFamily: "Consolas, monospace",
            fontSize: 14,
            fontWeight: 800,
            color: theme.accent1,
            letterSpacing: 1.4,
            whiteSpace: "nowrap",
            boxShadow: isQuantum
              ? `0 5px 0 rgba(2,6,18,0.9), 0 0 28px ${theme.accent1}44, inset 0 1px 2px rgba(255,255,255,0.28)`
              : `0 0 22px ${theme.accent1}28`,
          }}
        >
          {badge}
        </div>
      )}
    </div>
  );
};

/* ============================================================================
 * 1) LEDGER_LAYERS: Isometric 3D glass-plate stack with inflated 3D shelves,
 *    floating detached numbers/labels & concave pull-to-center framing.
 * ============================================================================ */
export const LedgerLayersSlide: React.FC<StorySlideProps> = ({ slide, dur, theme, isPortrait }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const isQuantum = theme.id === "quantum_ledger";
  const layers = slide.layers ?? [];
  const count = Math.max(1, layers.length);
  const accents = [theme.accent1, "#a855f7", theme.accent4, theme.accent2, theme.accent3, theme.accent1];

  const usable = Math.max(1, dur - 24);
  const progress = interpolate(frame, [12, 12 + usable], [0, count - 0.001], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const activeIdx = Math.min(count - 1, Math.max(0, Math.floor(progress)));
  const camYaw = -16 + Math.sin(frame / 52) * 2.4;
  const camPitch = 44 + Math.cos(frame / 64) * 1.8;

  if (isPortrait) {
    return (
      <div style={{ width: "100%", display: "flex", flexDirection: "column", gap: 20 }}>
        <StoryHeading
          title={slide.title}
          subtitle={slide.subtitle}
          badge={`${count} LAYERS · FAIL-CLOSED`}
          theme={theme}
          isPortrait
        />
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {layers.map((layer, idx) => {
            const color = layer.accent ?? accents[idx % accents.length];
            const isActive = idx === activeIdx;
            const s = spring({ frame: frame - (6 + idx * 6), fps, config: { damping: 180 } });
            return (
              <div
                key={layer.id}
                style={{
                  opacity: s,
                  padding: "16px 20px",
                  borderRadius: 18,
                  background: inflatedCardBg(color, isActive, theme.cardBg, isQuantum),
                  border: `${isActive ? 2 : 1.5}px solid ${isActive ? color : theme.cardBorder}`,
                  boxShadow: inflatedCardShadow(color, isActive, isQuantum),
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span
                    style={{
                      fontSize: 22,
                      fontWeight: 900,
                      color: isActive ? "#ffffff" : theme.text,
                      textShadow: isQuantum ? floatTextShadow(color) : undefined,
                    }}
                  >
                    {String(idx + 1).padStart(2, "0")} · {layer.name}
                  </span>
                  <span style={{ fontSize: 13, fontFamily: "Consolas, monospace", color, fontWeight: 800 }}>
                    {layer.tech}
                  </span>
                </div>
                <div style={{ fontSize: 18, color: theme.muted, marginTop: 6 }}>{layer.desc}</div>
                <div style={{ fontSize: 16, color: theme.text, marginTop: 6, fontWeight: 700 }}>
                  ✓ {layer.guarantee}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  // Landscape 1920x1080
  const stageW = 820;
  const stageH = 620;
  const plateW = 552;
  const plateH = 114;
  const gapY = count <= 4 ? 116 : count === 5 ? 96 : 82;
  const startTop = Math.max(20, (stageH - (count - 1) * gapY - plateH) / 2 - 14);

  return (
    <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", gap: 18 }}>
      <StoryHeading
        title={slide.title}
        subtitle={slide.subtitle}
        badge={`3D LEDGER STACK · ${count} LAYERS`}
        theme={theme}
        isPortrait={false}
      />

      <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 36, perspective: 1800 }}>
        {/* Left: Isometric 3D inflated glass plates pulled gently toward the center */}
        <div
          style={{
            width: stageW,
            height: stageH,
            position: "relative",
            perspective: 1550,
            flexShrink: 0,
            transform: isQuantum ? "rotateY(6deg)" : undefined,
          }}
        >
          {/* Ambient vertical multi-color data beams running down into RocksDB */}
          <svg
            width={stageW}
            height={stageH}
            style={{ position: "absolute", inset: 0, overflow: "visible", pointerEvents: "none" }}
          >
            <defs>
              <linearGradient id="layerBeam" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={theme.accent1} stopOpacity="0.95" />
                <stop offset="50%" stopColor={theme.accent2} stopOpacity="0.95" />
                <stop offset="100%" stopColor={theme.accent3} stopOpacity="1" />
              </linearGradient>
              <filter id="layerGlow" x="-50%" y="-50%" width="200%" height="200%">
                <feGaussianBlur stdDeviation="5.5" result="b" />
                <feMerge>
                  <feMergeNode in="b" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>
            {[stageW * 0.25, stageW * 0.5, stageW * 0.75].map((cx, rIdx) => {
              const y1 = startTop + 26;
              const y2 = startTop + (count - 1) * gapY + 78;
              const pulseT = (frame * 0.02 + rIdx * 0.33) % 1;
              const py = y1 + (y2 - y1) * pulseT;
              const pulseColor = [theme.accent1, theme.accent2, theme.accent3][rIdx % 3];
              return (
                <g key={rIdx}>
                  <line
                    x1={cx}
                    y1={y1}
                    x2={cx}
                    y2={y2}
                    stroke="url(#layerBeam)"
                    strokeWidth={rIdx === 1 ? 3.5 : 1.8}
                    strokeDasharray={rIdx === 1 ? "none" : "6 8"}
                    opacity={rIdx === 1 ? 0.65 : 0.38}
                  />
                  <line
                    x1={cx}
                    y1={Math.max(y1, py - 55)}
                    x2={cx}
                    y2={py}
                    stroke={pulseColor}
                    strokeWidth={rIdx === 1 ? 5 : 3}
                    strokeLinecap="round"
                    filter="url(#layerGlow)"
                    opacity={0.9}
                  />
                  <circle cx={cx} cy={py} r={rIdx === 1 ? 7.5 : 5} fill="#ffffff" filter="url(#layerGlow)" />
                </g>
              );
            })}
          </svg>

          {[...layers].reverse().map((layer, revIdx) => {
            const idx = count - 1 - revIdx;
            const color = layer.accent ?? accents[idx % accents.length];
            const isActive = idx === activeIdx;
            const isPassed = idx < activeIdx;
            const entry = spring({ frame: frame - (4 + idx * 5), fps, config: { damping: 160 } });
            const activePop = spring({
              frame: isActive ? frame - Math.round(12 + (idx * usable) / count) : 0,
              fps,
              config: { damping: 140 },
            });
            const shiftX = isActive ? 28 * activePop : 0;
            const liftY = isActive ? -10 * activePop : 0;
            const topPos = startTop + idx * gapY + liftY;
            const leftPos = (stageW - plateW) / 2 - 12 + shiftX;

            return (
              <div
                key={layer.id}
                style={{
                  position: "absolute",
                  left: leftPos,
                  top: topPos,
                  width: plateW,
                  height: plateH,
                  opacity: interpolate(entry, [0, 1], [0, isActive ? 1 : isPassed ? 0.94 : 0.72]),
                  transformStyle: "preserve-3d",
                  transform: `rotateX(${camPitch}deg) rotateZ(${camYaw}deg) translateY(${interpolate(entry, [0, 1], [34, 0])}px) scale(${isActive ? 1.05 : 1})`,
                  borderRadius: 22,
                  background: inflatedCardBg(color, isActive, theme.cardBg, isQuantum),
                  border: `${isActive ? 2.5 : 1.5}px solid ${isActive ? color : isPassed ? `${color}99` : theme.cardBorder}`,
                  boxShadow: isActive
                    ? `0 14px 0 rgba(3,8,24,0.95), 0 18px 0 ${color}77, 0 34px 66px rgba(0,0,0,0.78), 0 0 46px ${color}66, inset 0 2px 4px rgba(255,255,255,0.34), inset 0 -10px 20px rgba(0,0,0,0.5)`
                    : `0 11px 0 rgba(3,9,22,0.92), 0 22px 40px rgba(0,0,0,0.6), inset 0 1.5px 2px rgba(255,255,255,0.16)`,
                  padding: "16px 26px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 18, transformStyle: "preserve-3d" }}>
                  {/* Detached floating number cube */}
                  <div
                    style={{
                      width: 52,
                      height: 52,
                      borderRadius: 15,
                      background: isActive
                        ? `radial-gradient(circle at 35% 25%, #ffffff 0%, ${color} 45%, ${color}cc 100%)`
                        : `${color}2e`,
                      border: `2px solid ${color}`,
                      color: isActive ? "#020512" : "#ffffff",
                      fontWeight: 900,
                      fontSize: 22,
                      fontFamily: "Consolas, monospace",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      transform: isQuantum ? "translateZ(26px) translateY(-4px)" : undefined,
                      boxShadow: isActive
                        ? `0 8px 18px rgba(0,0,0,0.85), 0 0 28px ${color}`
                        : `0 6px 14px rgba(0,0,0,0.75)`,
                      flexShrink: 0,
                    }}
                  >
                    {String(idx + 1).padStart(2, "0")}
                  </div>
                  <div style={{ transform: isQuantum ? "translateZ(20px)" : undefined }}>
                    <div
                      style={{
                        fontSize: 25,
                        fontWeight: 900,
                        color: "#ffffff",
                        letterSpacing: 0.2,
                        textShadow: isQuantum ? floatTextShadow(color) : undefined,
                      }}
                    >
                      {layer.name}
                    </div>
                    <div
                      style={{
                        fontSize: 15,
                        fontFamily: "Consolas, monospace",
                        color,
                        marginTop: 4,
                        fontWeight: 800,
                        textShadow: isQuantum ? `0 4px 10px rgba(0,0,0,0.9)` : undefined,
                      }}
                    >
                      {layer.tech}
                    </div>
                  </div>
                </div>
                <div
                  style={{
                    padding: "6px 13px",
                    borderRadius: 999,
                    background: isActive || isPassed ? `${color}30` : "rgba(255,255,255,0.06)",
                    border: `1.5px solid ${isActive || isPassed ? color : theme.cardBorder}`,
                    fontFamily: "Consolas, monospace",
                    fontSize: 13,
                    fontWeight: 900,
                    color: isActive ? "#ffffff" : isPassed ? theme.accent2 : theme.muted,
                    transform: isQuantum ? "translateZ(22px)" : undefined,
                    boxShadow: isActive ? `0 8px 16px rgba(0,0,0,0.8), 0 0 18px ${color}` : undefined,
                  }}
                >
                  {isActive ? "ACTIVE" : isPassed ? "SEALED ✓" : `L${idx + 1}`}
                </div>
              </div>
            );
          })}
        </div>

        {/* Right: Concave-angled inflated breakdown cards with detached floating numbers */}
        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            gap: 12,
            transform: isQuantum ? "rotateY(-6.5deg)" : undefined,
            transformStyle: "preserve-3d",
          }}
        >
          {layers.map((layer, idx) => {
            const color = layer.accent ?? accents[idx % accents.length];
            const isActive = idx === activeIdx;
            const isPassed = idx < activeIdx;
            const s = spring({ frame: frame - (8 + idx * 5), fps, config: { damping: 180 } });
            return (
              <div
                key={layer.id}
                style={{
                  opacity: interpolate(s, [0, 1], [0, isActive ? 1 : isPassed ? 0.88 : 0.68]),
                  transform: `translateX(${interpolate(s, [0, 1], [28, isActive ? -8 : 0])}px)`,
                  padding: isActive ? "16px 22px" : "12px 18px",
                  borderRadius: 18,
                  background: inflatedCardBg(color, isActive, theme.cardBg, isQuantum),
                  border: `${isActive ? 2 : 1.5}px solid ${isActive ? color : theme.cardBorder}`,
                  boxShadow: inflatedCardShadow(color, isActive, isQuantum),
                  transformStyle: "preserve-3d",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <span
                      style={{
                        fontFamily: "Consolas, monospace",
                        fontSize: isActive ? 18 : 15,
                        fontWeight: 900,
                        color,
                        textShadow: isQuantum ? floatTextShadow(color) : undefined,
                      }}
                    >
                      {String(idx + 1).padStart(2, "0")}
                    </span>
                    <span
                      style={{
                        fontSize: isActive ? 24 : 20,
                        fontWeight: 900,
                        color: "#ffffff",
                        textShadow: isQuantum && isActive ? floatTextShadow(color) : undefined,
                      }}
                    >
                      {layer.name}
                    </span>
                  </div>
                  <span
                    style={{
                      fontSize: 13,
                      fontFamily: "Consolas, monospace",
                      color,
                      fontWeight: 800,
                      whiteSpace: "nowrap",
                    }}
                  >
                    {layer.tech}
                  </span>
                </div>
                <div style={{ fontSize: 17, color: theme.muted, marginTop: 4, lineHeight: 1.32 }}>{layer.desc}</div>
                {isActive && (
                  <div
                    style={{
                      marginTop: 9,
                      padding: "8px 13px",
                      borderRadius: 12,
                      background: `${color}22`,
                      borderLeft: `4px solid ${color}`,
                      fontSize: 16.5,
                      fontWeight: 700,
                      color: "#ffffff",
                      boxShadow: "0 6px 14px rgba(0,0,0,0.45)",
                    }}
                  >
                    <span style={{ color, marginRight: 8, fontWeight: 900 }}>ГАРАНТИЯ:</span>
                    {layer.guarantee}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

/* ============================================================================
 * 2) TX_JOURNEY: Animated transaction light-beam lifecycle + golden Merkle tree +
 *    inflated 3D chained blocks sealing green with RocksDB stamp.
 * ============================================================================ */
export const TxJourneySlide: React.FC<StorySlideProps> = ({ slide, dur, theme, isPortrait }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const isQuantum = theme.id === "quantum_ledger";
  const j = slide.journey;
  if (!j) return null;

  const steps = j.steps;
  const blocks = j.blocks;
  const leaves = j.merkle_leaves ?? ["tx·a41f", "tx·9c02", "tx·e718", "TX* NEW"];
  const stepCount = Math.max(1, steps.length);
  const accents = [theme.accent1, theme.accent4, theme.accent3, theme.accent2, theme.accent1];
  const greenCol = isQuantum ? "#10ff88" : theme.accent3;
  const goldCol = isQuantum ? "#ffb800" : theme.accent3;

  const usable = Math.max(1, dur - 24);
  const progress = interpolate(frame, [10, 10 + usable], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const activeStep = Math.min(stepCount - 1, Math.floor(progress * stepCount));
  const merkleLevel1 = interpolate(progress, [0.32, 0.46], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const merkleRootVis = interpolate(progress, [0.46, 0.58], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const blockSealed = progress >= 0.62;
  const sealSpring = spring({
    frame: blockSealed ? frame - Math.round(10 + usable * 0.62) : 0,
    fps,
    config: { damping: 140 },
  });

  if (isPortrait) {
    return (
      <div style={{ width: "100%", display: "flex", flexDirection: "column", gap: 18 }}>
        <StoryHeading
          title={slide.title}
          subtitle={slide.subtitle}
          badge={`${j.tx_label} · ${j.amount_label}`}
          theme={theme}
          isPortrait
        />
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {steps.map((st, idx) => {
            const color = st.accent ?? accents[idx % accents.length];
            const isActive = idx === activeStep;
            return (
              <div
                key={st.title}
                style={{
                  padding: "14px 18px",
                  borderRadius: 18,
                  background: inflatedCardBg(color, isActive, theme.cardBg, isQuantum),
                  border: `${isActive ? 2 : 1.5}px solid ${isActive ? color : theme.cardBorder}`,
                  boxShadow: inflatedCardShadow(color, isActive, isQuantum),
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: 21, fontWeight: 900, color: "#ffffff" }}>
                    {idx + 1}. {st.title}
                  </span>
                  <span style={{ fontSize: 13, fontFamily: "Consolas, monospace", color, fontWeight: 800 }}>
                    {st.badge}
                  </span>
                </div>
                <div style={{ fontSize: 17, color: theme.muted, marginTop: 5 }}>{st.detail}</div>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  // Landscape 1920x1080
  const pipeW = 1720;
  const packetX = interpolate(progress, [0, 1], [110, pipeW - 110], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const activeColor = steps[activeStep]?.accent ?? accents[activeStep % accents.length];

  return (
    <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", gap: 16 }}>
      <StoryHeading
        title={slide.title}
        subtitle={slide.subtitle}
        badge={`${j.tx_label}  ·  ${j.amount_label}  ·  ${j.signature_label}`}
        theme={theme}
        isPortrait={false}
      />

      {/* Middle Stage: Concave 3D pairing — Left Golden Merkle Tree + Right Inflated Block Chain */}
      <div style={{ display: "flex", gap: 22, height: 356, alignItems: "stretch", perspective: 1800 }}>
        {/* Merkle Tree panel (angled gently toward center) */}
        <div
          style={{
            width: 560,
            flexShrink: 0,
            borderRadius: 22,
            background: inflatedCardBg(goldCol, merkleRootVis > 0.3, theme.cardBg, isQuantum),
            border: `2px solid ${merkleRootVis > 0.3 ? goldCol : theme.cardBorder}`,
            boxShadow: inflatedCardShadow(goldCol, merkleRootVis > 0.3, isQuantum),
            padding: "16px 20px",
            position: "relative",
            overflow: "hidden",
            transform: isQuantum ? "rotateY(5deg)" : undefined,
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
            <span
              style={{
                fontFamily: "Consolas, monospace",
                fontSize: 13.5,
                fontWeight: 900,
                color: goldCol,
                letterSpacing: 1.5,
                textShadow: isQuantum ? floatTextShadow(goldCol) : undefined,
              }}
            >
              MERKLE &amp; STATE ROOT
            </span>
            <span style={{ fontFamily: "Consolas, monospace", fontSize: 12, color: theme.muted }}>
              SHA-256 · abs_native
            </span>
          </div>

          <svg width={520} height={290} viewBox="0 0 520 262" style={{ display: "block", width: "100%", height: 290 }}>
            <defs>
              <filter id="mkGlow" x="-40%" y="-40%" width="180%" height="180%">
                <feGaussianBlur stdDeviation="4" result="b" />
                <feMerge>
                  <feMergeNode in="b" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>

            {/* Exact box-edge Merkle branches */}
            {[
              { x1: 68, y1: 208, x2: 140, y2: 144, vis: merkleLevel1, c: theme.accent1 },
              { x1: 196, y1: 208, x2: 140, y2: 144, vis: merkleLevel1, c: theme.accent1 },
              { x1: 324, y1: 208, x2: 380, y2: 144, vis: merkleLevel1, c: greenCol },
              { x1: 452, y1: 208, x2: 380, y2: 144, vis: merkleLevel1, c: greenCol },
              { x1: 140, y1: 104, x2: 260, y2: 54, vis: merkleRootVis, c: goldCol },
              { x1: 380, y1: 104, x2: 260, y2: 54, vis: merkleRootVis, c: goldCol },
            ].map((br, i) => (
              <g key={i}>
                <line
                  x1={br.x1}
                  y1={br.y1}
                  x2={br.x2}
                  y2={br.y2}
                  stroke={br.vis > 0.1 ? br.c : "rgba(255,255,255,0.16)"}
                  strokeWidth={br.vis > 0.1 ? 2.8 : 1.5}
                  opacity={0.35 + br.vis * 0.65}
                />
                {br.vis > 0.05 && br.vis < 0.99 && (
                  <circle
                    cx={br.x1 + (br.x2 - br.x1) * br.vis}
                    cy={br.y1 + (br.y2 - br.y1) * br.vis}
                    r={5.5}
                    fill="#ffffff"
                    filter="url(#mkGlow)"
                  />
                )}
              </g>
            ))}

            {/* Root node */}
            <g opacity={0.4 + merkleRootVis * 0.6}>
              <rect
                x={126}
                y={10}
                width={268}
                height={44}
                rx={12}
                fill={merkleRootVis > 0.5 ? `${goldCol}36` : "rgba(10,20,46,0.9)"}
                stroke={goldCol}
                strokeWidth={merkleRootVis > 0.5 ? 2.2 : 1.2}
              />
              <text x={260} y={30} textAnchor="middle" fill={goldCol} fontSize={12.5} fontWeight={900} fontFamily="Consolas, monospace">
                MERKLE + STATE ROOT
              </text>
              <text x={260} y={46} textAnchor="middle" fill="#ffffff" fontSize={12} fontFamily="Consolas, monospace">
                0x9fd8a7...b62867e
              </text>
            </g>

            {/* Pair hashes */}
            {[
              { x: 64, label: "H(tx1, tx2)", val: "0x4a8c...", c: theme.accent1 },
              { x: 304, label: "H(tx3, TX*)", val: "0x7f1e...", c: greenCol },
            ].map((h, i) => (
              <g key={i} opacity={0.4 + merkleLevel1 * 0.6}>
                <rect
                  x={h.x}
                  y={104}
                  width={152}
                  height={40}
                  rx={10}
                  fill={merkleLevel1 > 0.5 ? `${h.c}2b` : "rgba(10,20,46,0.88)"}
                  stroke={h.c}
                  strokeWidth={1.6}
                />
                <text x={h.x + 76} y={121} textAnchor="middle" fill={h.c} fontSize={12} fontWeight={900} fontFamily="Consolas, monospace">
                  {h.label}
                </text>
                <text x={h.x + 76} y={136} textAnchor="middle" fill="#ffffff" fontSize={11} fontFamily="Consolas, monospace">
                  {h.val}
                </text>
              </g>
            ))}

            {/* 4 Leaf transactions */}
            {leaves.slice(0, 4).map((lf, i) => {
              const lx = 14 + i * 128;
              const isOurs = i === leaves.slice(0, 4).length - 1;
              const c = isOurs ? greenCol : theme.accent1;
              return (
                <g key={i}>
                  <rect
                    x={lx}
                    y={208}
                    width={108}
                    height={42}
                    rx={10}
                    fill={isOurs ? `${greenCol}33` : "rgba(10,20,46,0.88)"}
                    stroke={c}
                    strokeWidth={isOurs ? 2.2 : 1.3}
                  />
                  <text
                    x={lx + 54}
                    y={233}
                    textAnchor="middle"
                    fill={isOurs ? "#ffffff" : theme.text}
                    fontSize={12.5}
                    fontWeight={isOurs ? 900 : 700}
                    fontFamily="Consolas, monospace"
                  >
                    {lf}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>

        {/* Right: Inflated 3D Block Chain (angled gently toward center) */}
        <div
          style={{
            flex: 1,
            borderRadius: 22,
            background: inflatedCardBg(greenCol, blockSealed, theme.cardBg, isQuantum),
            border: `2px solid ${blockSealed ? greenCol : theme.cardBorder}`,
            boxShadow: inflatedCardShadow(greenCol, blockSealed, isQuantum),
            padding: "16px 24px",
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
            transform: isQuantum ? "rotateY(-4.5deg)" : undefined,
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span
              style={{
                fontFamily: "Consolas, monospace",
                fontSize: 13.5,
                fontWeight: 900,
                color: theme.accent1,
                letterSpacing: 1.5,
                textShadow: isQuantum ? floatTextShadow(theme.accent1) : undefined,
              }}
            >
              IMMUTABLE BLOCK CHAIN · PREV_HASH LINKED
            </span>
            <span
              style={{
                padding: "5px 13px",
                borderRadius: 999,
                background: blockSealed ? `${greenCol}2e` : `${goldCol}22`,
                border: `1.5px solid ${blockSealed ? greenCol : goldCol}`,
                fontFamily: "Consolas, monospace",
                fontSize: 12.5,
                fontWeight: 900,
                color: blockSealed ? greenCol : goldCol,
                boxShadow: blockSealed ? `0 0 20px ${greenCol}55` : undefined,
              }}
            >
              {blockSealed ? "ROCKSDB COMMITTED ✓" : "ASSEMBLING NEW BLOCK..."}
            </span>
          </div>

          <div
            style={{
              flex: 1,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 10,
              perspective: 1400,
              paddingTop: 10,
            }}
          >
            {blocks.map((blk, idx) => {
              const isNew = idx === blocks.length - 1;
              const sealedNow = !isNew || blockSealed;
              const borderColor = isNew ? (blockSealed ? greenCol : goldCol) : theme.accent1;
              const scale = isNew && blockSealed ? 1 + Math.sin(Math.min(1, sealSpring) * Math.PI) * 0.06 : 1;
              const pulse = (frame * 0.032 + idx * 0.27) % 1;
              return (
                <React.Fragment key={blk.height}>
                  <div
                    style={{
                      flex: 1,
                      height: 222,
                      borderRadius: 18,
                      background: inflatedCardBg(borderColor, isNew && blockSealed, "rgba(6,16,38,0.92)", isQuantum),
                      border: `${isNew ? 2.5 : 1.5}px ${sealedNow ? "solid" : "dashed"} ${borderColor}`,
                      boxShadow: isNew && blockSealed
                        ? `0 11px 0 rgba(2,10,22,0.95), 0 15px 0 ${greenCol}66, 0 0 38px ${greenCol}55, inset 0 2px 3px rgba(255,255,255,0.34)`
                        : `0 9px 0 rgba(2,8,20,0.92), 0 16px 32px rgba(0,0,0,0.58), inset 0 1.5px 2px rgba(255,255,255,0.16)`,
                      transform: `rotateY(-6deg) scale(${scale})`,
                      transformStyle: "preserve-3d",
                      padding: "14px 16px",
                      display: "flex",
                      flexDirection: "column",
                      justifyContent: "space-between",
                      opacity: isNew ? (blockSealed ? 1 : 0.78 + Math.sin(frame / 7) * 0.14) : 0.96,
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span
                        style={{
                          fontFamily: "Consolas, monospace",
                          fontSize: 21,
                          fontWeight: 900,
                          color: "#ffffff",
                          textShadow: isQuantum ? floatTextShadow(borderColor) : undefined,
                          transform: isQuantum ? "translateZ(20px)" : undefined,
                        }}
                      >
                        {blk.height}
                      </span>
                      <span
                        style={{
                          fontSize: 11.5,
                          fontFamily: "Consolas, monospace",
                          fontWeight: 900,
                          color: sealedNow ? greenCol : goldCol,
                        }}
                      >
                        {isNew ? (blockSealed ? "SEALED ✓" : "PENDING") : "FINAL"}
                      </span>
                    </div>

                    <div
                      style={{
                        padding: "9px 10px",
                        borderRadius: 11,
                        background: "rgba(2,6,18,0.68)",
                        border: `1px solid ${borderColor}44`,
                        fontFamily: "Consolas, monospace",
                        fontSize: 12.5,
                        color: "#ffffff",
                        boxShadow: "inset 0 2px 6px rgba(0,0,0,0.65)",
                      }}
                    >
                      <div style={{ fontSize: 10.5, color: theme.muted, marginBottom: 3 }}>BLOCK HASH</div>
                      <div>{blk.hash}</div>
                    </div>

                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, fontFamily: "Consolas, monospace", color: theme.muted }}>
                      <span>{blk.tx_count}</span>
                      <span style={{ color: borderColor, fontWeight: 800 }}>{isNew ? "TX* IN" : "LINKED"}</span>
                    </div>
                  </div>

                  {idx < blocks.length - 1 && (
                    <div style={{ width: 44, flexShrink: 0, display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
                      <svg width={44} height={26}>
                        <line
                          x1={2}
                          y1={13}
                          x2={42}
                          y2={13}
                          stroke={idx === blocks.length - 2 && !blockSealed ? goldCol : greenCol}
                          strokeWidth={3}
                          strokeDasharray={idx === blocks.length - 2 && !blockSealed ? "4 4" : "none"}
                        />
                        <circle cx={4 + pulse * 36} cy={13} r={4.5} fill="#ffffff" />
                      </svg>
                      <span style={{ fontSize: 10.5, fontFamily: "Consolas, monospace", color: theme.muted }}>prev</span>
                    </div>
                  )}
                </React.Fragment>
              );
            })}
          </div>
        </div>
      </div>

      {/* Bottom Stage: Animated Transaction Light-Beam Pipeline */}
      <div style={{ position: "relative", paddingTop: 48, display: "flex", flexDirection: "column", justifyContent: "flex-start" }}>
        <svg
          width={pipeW}
          height={54}
          viewBox={`0 0 ${pipeW} 54`}
          style={{ position: "absolute", top: 6, left: 0, width: "100%", height: 54, overflow: "visible" }}
        >
          <defs>
            <linearGradient id="txRail" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor={theme.accent1} />
              <stop offset="30%" stopColor={theme.accent4} />
              <stop offset="65%" stopColor={goldCol} />
              <stop offset="100%" stopColor={greenCol} />
            </linearGradient>
            <filter id="txPktGlow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="6" result="b" />
              <feMerge>
                <feMergeNode in="b" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
          <line x1={110} y1={22} x2={pipeW - 110} y2={22} stroke="rgba(255,255,255,0.14)" strokeWidth={5.5} strokeLinecap="round" />
          <line
            x1={110}
            y1={22}
            x2={Math.max(110, packetX)}
            y2={22}
            stroke="url(#txRail)"
            strokeWidth={5.5}
            strokeLinecap="round"
          />
          {steps.map((st, idx) => {
            const sx = stepCount > 1 ? 110 + ((pipeW - 220) * idx) / (stepCount - 1) : pipeW / 2;
            const c = st.accent ?? accents[idx % accents.length];
            const lit = idx <= activeStep;
            return (
              <g key={st.title}>
                <line x1={sx} y1={22} x2={sx} y2={48} stroke={lit ? c : "rgba(255,255,255,0.18)"} strokeWidth={2.5} />
                <circle cx={sx} cy={22} r={lit ? 6.5 : 4.5} fill={lit ? c : "rgba(255,255,255,0.24)"} />
              </g>
            );
          })}
          {/* Glowing transaction light-beam comet traveling across steps */}
          <g transform={`translate(${packetX}, 22)`}>
            <line x1={-68} y1={0} x2={0} y2={0} stroke={activeColor} strokeWidth={8} strokeLinecap="round" opacity={0.45} filter="url(#txPktGlow)" />
            <circle r={15} fill={activeColor} opacity={0.42} filter="url(#txPktGlow)" />
            <circle r={9} fill="#ffffff" stroke={activeColor} strokeWidth={2.5} />
          </g>
        </svg>

        {/* Inflated Step Cards with floating detached numbers/titles */}
        <div style={{ display: "flex", gap: 14, width: "100%", marginTop: 10 }}>
          {steps.map((st, idx) => {
            const color = st.accent ?? accents[idx % accents.length];
            const isActive = idx === activeStep;
            const isDone = idx < activeStep;
            return (
              <div
                key={st.title}
                style={{
                  flex: 1,
                  minHeight: 178,
                  padding: "16px 18px",
                  borderRadius: 18,
                  background: inflatedCardBg(color, isActive, theme.cardBg, isQuantum),
                  border: `${isActive ? 2.5 : 1.5}px solid ${isActive ? color : isDone ? `${color}88` : theme.cardBorder}`,
                  boxShadow: inflatedCardShadow(color, isActive, isQuantum),
                  transform: `translateY(${isActive ? -8 : 0}px)`,
                  opacity: isActive || isDone ? 1 : 0.7,
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "space-between",
                }}
              >
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                    <span
                      style={{
                        fontFamily: "Consolas, monospace",
                        fontSize: 13.5,
                        fontWeight: 900,
                        color,
                        textShadow: isQuantum ? floatTextShadow(color) : undefined,
                      }}
                    >
                      0{idx + 1} · {st.badge}
                    </span>
                    {isDone && (
                      <span style={{ color: greenCol, fontWeight: 900, fontSize: 17, textShadow: `0 0 12px ${greenCol}` }}>
                        ✓
                      </span>
                    )}
                  </div>
                  <div
                    style={{
                      fontSize: 23,
                      fontWeight: 900,
                      color: "#ffffff",
                      lineHeight: 1.18,
                      textShadow: isQuantum && isActive ? floatTextShadow(color) : undefined,
                    }}
                  >
                    {st.title}
                  </div>
                </div>
                <div style={{ fontSize: 16.5, color: theme.muted, marginTop: 8, lineHeight: 1.34 }}>{st.detail}</div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

/* ============================================================================
 * 3) MESH_NETWORK: 3D 3-node mesh topology with encrypted libp2p light beams,
 *    wire probe pulses, concave framing & inflated guarantee shelves.
 * ============================================================================ */
export const MeshNetworkSlide: React.FC<StorySlideProps> = ({ slide, dur, theme, isPortrait }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const isQuantum = theme.id === "quantum_ledger";
  const m = slide.mesh;
  if (!m) return null;

  const nodes = m.nodes;
  const recovery = m.recovery_steps;
  const greenCol = isQuantum ? "#10ff88" : theme.accent3;
  const accents = [theme.accent1, greenCol, theme.accent3, theme.accent4];
  const usable = Math.max(1, dur - 24);
  const progress = interpolate(frame, [10, 10 + usable], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const activeRecovery = Math.min(Math.max(0, recovery.length - 1), Math.floor(progress * Math.max(1, recovery.length)));
  const aligned = progress >= 0.48;

  if (isPortrait) {
    return (
      <div style={{ width: "100%", display: "flex", flexDirection: "column", gap: 20 }}>
        <StoryHeading
          title={slide.title}
          subtitle={slide.subtitle}
          badge={`${m.protocol_label} · ${m.chain_id}`}
          theme={theme}
          isPortrait
        />
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {nodes.map((n, idx) => (
            <div
              key={n.id}
              style={{
                padding: "14px 18px",
                borderRadius: 18,
                background: inflatedCardBg(accents[idx % accents.length], true, theme.cardBg, isQuantum),
                border: `1.5px solid ${accents[idx % accents.length]}`,
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <div>
                <div style={{ fontSize: 21, fontWeight: 900, color: "#ffffff" }}>{n.id}</div>
                <div style={{ fontSize: 15, color: theme.muted, fontFamily: "Consolas, monospace" }}>
                  {n.role} · {n.endpoint}
                </div>
              </div>
              <span style={{ fontSize: 14, fontFamily: "Consolas, monospace", color: greenCol, fontWeight: 900 }}>
                {n.status}
              </span>
            </div>
          ))}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {recovery.map((r, idx) => (
            <div
              key={r.title}
              style={{
                padding: "14px 18px",
                borderRadius: 18,
                background: inflatedCardBg(accents[idx % accents.length], idx === activeRecovery, theme.cardBg, isQuantum),
                border: `1.5px solid ${theme.cardBorder}`,
              }}
            >
              <div style={{ fontSize: 20, fontWeight: 900, color: accents[idx % accents.length] }}>{r.title}</div>
              <div style={{ fontSize: 17, color: theme.muted, marginTop: 4 }}>{r.desc}</div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // Landscape 1920x1080
  const stageW = 920;
  const stageH = 600;
  const cardW = 286;
  const cardH = 152;
  const coords =
    nodes.length === 4
      ? [
          { cx: 460, cy: 105 },
          { cx: 180, cy: 300 },
          { cx: 740, cy: 300 },
          { cx: 460, cy: 495 },
        ]
      : [
          { cx: 460, cy: 112 },
          { cx: 190, cy: 468 },
          { cx: 730, cy: 468 },
        ];

  const links: Array<{ a: number; b: number }> = [];
  for (let i = 0; i < Math.min(nodes.length, coords.length); i++) {
    for (let j = i + 1; j < Math.min(nodes.length, coords.length); j++) {
      links.push({ a: i, b: j });
    }
  }

  return (
    <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", gap: 18 }}>
      <StoryHeading
        title={slide.title}
        subtitle={slide.subtitle}
        badge={`${m.protocol_label}  ·  CHAIN ${m.chain_id}`}
        theme={theme}
        isPortrait={false}
      />

      <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 36, perspective: 1800 }}>
        {/* Left: Concave 3D Mesh Stage */}
        <div
          style={{
            width: stageW,
            height: stageH,
            position: "relative",
            flexShrink: 0,
            perspective: 1500,
            transform: isQuantum ? "rotateY(5.5deg)" : undefined,
          }}
        >
          <div
            style={{
              position: "absolute",
              left: 34,
              right: 34,
              top: 46,
              bottom: 24,
              borderRadius: 28,
              border: `1.5px solid ${theme.accent1}44`,
              background: `radial-gradient(circle at 50% 54%, ${greenCol}1f 0%, rgba(4,12,32,0.72) 70%)`,
              backgroundImage: `linear-gradient(${theme.accent1}18 1px, transparent 1px), linear-gradient(90deg, ${greenCol}16 1px, transparent 1px)`,
              backgroundSize: "44px 44px",
              transform: "rotateX(22deg)",
              boxShadow: "inset 0 0 65px rgba(0,0,0,0.55), 0 32px 72px rgba(0,0,0,0.52)",
            }}
          />

          <svg
            width={stageW}
            height={stageH}
            style={{ position: "absolute", inset: 0, overflow: "visible", pointerEvents: "none" }}
          >
            <defs>
              <filter id="meshGlow" x="-50%" y="-50%" width="200%" height="200%">
                <feGaussianBlur stdDeviation="5" result="b" />
                <feMerge>
                  <feMergeNode in="b" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>
            {links.map((lk, idx) => {
              const p1 = coords[lk.a];
              const p2 = coords[lk.b];
              const fwd = (frame * 0.024 + idx * 0.31) % 1;
              const rev = (frame * 0.019 + idx * 0.43 + 0.5) % 1;
              const fx = p1.cx + (p2.cx - p1.cx) * fwd;
              const fy = p1.cy + (p2.cy - p1.cy) * fwd;
              const rx = p2.cx + (p1.cx - p2.cx) * rev;
              const ry = p2.cy + (p1.cy - p2.cy) * rev;
              return (
                <g key={`${lk.a}-${lk.b}`}>
                  <line
                    x1={p1.cx}
                    y1={p1.cy}
                    x2={p2.cx}
                    y2={p2.cy}
                    stroke={aligned ? greenCol : theme.accent1}
                    strokeWidth={3.2}
                    opacity={0.55}
                    strokeDasharray="10 7"
                    strokeDashoffset={-frame * 1.6}
                  />
                  <circle cx={fx} cy={fy} r={8} fill="#ffffff" stroke={theme.accent1} strokeWidth={2.5} filter="url(#meshGlow)" />
                  <circle cx={rx} cy={ry} r={6.5} fill={greenCol} filter="url(#meshGlow)" />
                </g>
              );
            })}
          </svg>

          {/* Center floating probe hub */}
          <div
            style={{
              position: "absolute",
              left: stageW / 2 - 156,
              top: stageH / 2 - 36,
              width: 312,
              padding: "13px 16px",
              borderRadius: 18,
              background: inflatedCardBg(aligned ? greenCol : theme.accent1, true, "rgba(3,10,28,0.94)", isQuantum),
              border: `2px solid ${aligned ? greenCol : theme.accent1}`,
              boxShadow: inflatedCardShadow(aligned ? greenCol : theme.accent1, true, isQuantum),
              textAlign: "center",
            }}
          >
            <div style={{ fontFamily: "Consolas, monospace", fontSize: 12.5, fontWeight: 900, color: theme.accent1, letterSpacing: 1.4 }}>
              {m.protocol_label}
            </div>
            <div
              style={{
                fontFamily: "Consolas, monospace",
                fontSize: 14.5,
                fontWeight: 900,
                color: greenCol,
                marginTop: 5,
                textShadow: isQuantum ? floatTextShadow(greenCol) : undefined,
              }}
            >
              {m.probe_label}
            </div>
          </div>

          {/* Inflated 3D Node Towers */}
          {nodes.slice(0, coords.length).map((node, idx) => {
            const pos = coords[idx];
            const color = accents[idx % accents.length];
            const s = spring({ frame: frame - (6 + idx * 8), fps, config: { damping: 165 } });
            const pulse = 0.65 + Math.sin(frame / 10 + idx * 1.6) * 0.35;
            return (
              <div
                key={node.id}
                style={{
                  position: "absolute",
                  left: pos.cx - cardW / 2,
                  top: pos.cy - cardH / 2,
                  width: cardW,
                  height: cardH,
                  opacity: s,
                  transform: `scale(${interpolate(s, [0, 1], [0.9, 1])})`,
                  borderRadius: 20,
                  background: inflatedCardBg(color, true, "rgba(5,14,34,0.95)", isQuantum),
                  border: `2.5px solid ${color}`,
                  boxShadow: inflatedCardShadow(color, true, isQuantum),
                  padding: "14px 18px",
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "space-between",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
                    <div
                      style={{
                        width: 12,
                        height: 12,
                        borderRadius: "50%",
                        background: greenCol,
                        boxShadow: `0 0 14px ${greenCol}`,
                        opacity: pulse,
                      }}
                    />
                    <span
                      style={{
                        fontSize: 24,
                        fontWeight: 900,
                        color: "#ffffff",
                        textShadow: isQuantum ? floatTextShadow(color) : undefined,
                      }}
                    >
                      {node.id}
                    </span>
                  </div>
                  <span
                    style={{
                      fontFamily: "Consolas, monospace",
                      fontSize: 12,
                      fontWeight: 900,
                      color: greenCol,
                      padding: "4px 10px",
                      borderRadius: 999,
                      background: `${greenCol}24`,
                      border: `1.5px solid ${greenCol}aa`,
                    }}
                  >
                    {node.status}
                  </span>
                </div>

                <div style={{ fontSize: 16.5, color: theme.muted, fontWeight: 600 }}>{node.role}</div>

                <div style={{ display: "flex", justifyContent: "space-between", fontFamily: "Consolas, monospace", fontSize: 13.5, color, fontWeight: 800 }}>
                  <span>{node.endpoint}</span>
                  {node.height && (
                    <span style={{ color: "#ffffff", textShadow: isQuantum ? floatTextShadow(color) : undefined }}>
                      h={node.height}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Right: Concave-angled inflated guarantee shelves */}
        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            gap: 18,
            transform: isQuantum ? "rotateY(-6.5deg)" : undefined,
          }}
        >
          {recovery.map((item, idx) => {
            const color = item.accent ?? accents[idx % accents.length];
            const isActive = idx === activeRecovery;
            const s = spring({ frame: frame - (12 + idx * 10), fps, config: { damping: 180 } });
            return (
              <div
                key={item.title}
                style={{
                  opacity: s,
                  transform: `translateX(${interpolate(s, [0, 1], [30, isActive ? -8 : 0])}px)`,
                  padding: "20px 24px",
                  borderRadius: 20,
                  background: inflatedCardBg(color, isActive, theme.cardBg, isQuantum),
                  border: `${isActive ? 2.5 : 1.5}px solid ${isActive ? color : theme.cardBorder}`,
                  boxShadow: inflatedCardShadow(color, isActive, isQuantum),
                }}
              >
                <div
                  style={{
                    fontFamily: "Consolas, monospace",
                    fontSize: 13.5,
                    fontWeight: 900,
                    color,
                    letterSpacing: 1.6,
                    marginBottom: 6,
                    textShadow: isQuantum ? floatTextShadow(color) : undefined,
                  }}
                >
                  0{idx + 1} · GUARANTEE
                </div>
                <div
                  style={{
                    fontSize: 26,
                    fontWeight: 900,
                    color: "#ffffff",
                    textShadow: isQuantum && isActive ? floatTextShadow(color) : undefined,
                  }}
                >
                  {item.title}
                </div>
                <div style={{ fontSize: 19, color: theme.muted, marginTop: 8, lineHeight: 1.38 }}>{item.desc}</div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

/* ============================================================================
 * 4) PROTOCOL_COSMOS: Flagship holographic full-system diagram — deep central
 *    crypto reactor (abs_native + RocksDB) surrounded by 6 concave inflated 3D
 *    stations, live light-beam transaction conduits & red fail-closed shield
 *    deflecting invalid packets in real time.
 * ============================================================================ */
export const ProtocolCosmosSlide: React.FC<StorySlideProps> = ({ slide, dur, theme, isPortrait }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const isQuantum = theme.id === "quantum_ledger";
  const c = slide.cosmos;
  if (!c) return null;

  const leftStations = c.stations.filter((s) => s.side === "left").slice(0, 3);
  const rightStations = c.stations.filter((s) => s.side === "right").slice(0, 3);
  const ordered = [...leftStations, ...rightStations];
  const usable = Math.max(1, dur - 24);
  const activeIdx = Math.min(ordered.length - 1, Math.max(0, Math.floor(interpolate(frame, [10, 10 + usable], [0, ordered.length - 0.001], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }))));
  const activeId = ordered[activeIdx]?.id;

  if (isPortrait) {
    return (
      <div style={{ width: "100%", display: "flex", flexDirection: "column", gap: 16 }}>
        <StoryHeading title={slide.title} subtitle={slide.subtitle} badge={c.core_title} theme={theme} isPortrait />
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {ordered.map((st) => {
            const isActive = st.id === activeId;
            return (
              <div
                key={st.id}
                style={{
                  padding: "13px 16px",
                  borderRadius: 16,
                  background: inflatedCardBg(st.color, isActive, theme.cardBg, isQuantum),
                  border: `${isActive ? 2 : 1.5}px solid ${st.color}`,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: 19, fontWeight: 900, color: "#ffffff" }}>{st.title}</span>
                  <span style={{ fontFamily: "Consolas, monospace", fontSize: 12, color: st.color, fontWeight: 800 }}>
                    {st.metric}
                  </span>
                </div>
                <div style={{ fontSize: 15.5, color: theme.muted, marginTop: 4 }}>{st.detail}</div>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  // Landscape 1920x1080 holographic reactor layout
  const stageW = 1764;
  const stageH = 650;
  const cx = stageW / 2;
  const cy = stageH / 2 + 4;
  const cardW = 470;
  const cardH = 166;

  // Concave arc positions: top & bottom slightly closer to edge, middle slightly wider so the center feels pulled inward
  const leftPos = [
    { x: 24, y: 40 },
    { x: 6, y: 248 },
    { x: 24, y: 456 },
  ];
  const rightPos = [
    { x: stageW - cardW - 24, y: 40 },
    { x: stageW - cardW - 6, y: 248 },
    { x: stageW - cardW - 24, y: 456 },
  ];

  // Animated rotation for the 4 concentric reactor rings
  const rot1 = frame * 0.7;
  const rot2 = -frame * 0.55;
  const rot3 = frame * 0.35;
  const corePulse = 1 + Math.sin(frame / 16) * 0.04;

  // Quadratic Bezier point helper for smooth light-beam travel between station and central reactor
  const quadPt = (p0: [number, number], p1: [number, number], p2: [number, number], t: number) => {
    const u = 1 - t;
    return {
      x: u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
      y: u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1],
    };
  };

  return (
    <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", gap: 12 }}>
      <StoryHeading
        title={slide.title}
        subtitle={slide.subtitle}
        badge="FULL PROTOCOL ARCHITECTURE · LIVE FLOW"
        theme={theme}
        isPortrait={false}
      />

      <div style={{ position: "relative", width: "100%", height: stageH, perspective: 1750 }}>
        {/* SVG Layer: Optical fiber conduits + traveling transaction light beams + red shield deflection */}
        <svg
          width={stageW}
          height={stageH}
          viewBox={`0 0 ${stageW} ${stageH}`}
          style={{ position: "absolute", inset: 0, width: "100%", height: "100%", overflow: "visible", pointerEvents: "none" }}
        >
          <defs>
            <filter id="cosmosGlow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="6" result="b" />
              <feMerge>
                <feMergeNode in="b" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <radialGradient id="reactorSphere" cx="42%" cy="35%" r="65%">
              <stop offset="0%" stopColor="#ffffff" stopOpacity="0.95" />
              <stop offset="22%" stopColor="#ffb800" stopOpacity="0.88" />
              <stop offset="58%" stopColor="#00f0ff" stopOpacity="0.45" />
              <stop offset="100%" stopColor="#020512" stopOpacity="0.92" />
            </radialGradient>
          </defs>

          {/* Conduits from 3 Left Stations -> Central Reactor */}
          {leftStations.map((st, idx) => {
            const p = leftPos[idx];
            const sx = p.x + cardW;
            const sy = p.y + cardH / 2;
            const ex = cx - 148;
            const ey = cy + (idx - 1) * 52;
            const ctrlX = (sx + ex) / 2 + 24;
            const ctrlY = (sy + ey) / 2;
            const isActive = st.id === activeId;
            const d = `M ${sx} ${sy} Q ${ctrlX} ${ctrlY} ${ex} ${ey}`;
            const t1 = (frame * 0.022 + idx * 0.31) % 1;
            const t2 = (frame * 0.022 + idx * 0.31 + 0.5) % 1;
            const pt1 = quadPt([sx, sy], [ctrlX, ctrlY], [ex, ey], t1);
            const pt2 = quadPt([sx, sy], [ctrlX, ctrlY], [ex, ey], t2);

            // Red shield station: show invalid red attack sparks deflecting off its outer barrier
            const isShield = st.role === "shield";
            const atkT = (frame * 0.028) % 1;
            const atkX = p.x - 75 + atkT * 78;
            const atkY = sy + Math.sin(frame / 8) * 14;

            return (
              <g key={`lc-${st.id}`}>
                <path
                  d={d}
                  fill="none"
                  stroke={st.color}
                  strokeWidth={isActive ? 4.2 : 2.6}
                  opacity={isActive ? 0.92 : 0.48}
                  filter={isActive ? "url(#cosmosGlow)" : undefined}
                />
                <path
                  d={d}
                  fill="none"
                  stroke="#ffffff"
                  strokeWidth={1.3}
                  strokeDasharray="8 14"
                  strokeDashoffset={-frame * 2.2}
                  opacity={0.75}
                />
                <circle cx={pt1.x} cy={pt1.y} r={isActive ? 8 : 6} fill="#ffffff" stroke={st.color} strokeWidth={2.5} filter="url(#cosmosGlow)" />
                <circle cx={pt2.x} cy={pt2.y} r={5} fill={st.color} filter="url(#cosmosGlow)" />
                {isShield && (
                  <g>
                    <circle cx={atkX} cy={atkY} r={5.5} fill="#ff2e63" filter="url(#cosmosGlow)" opacity={atkT < 0.85 ? 0.95 : 0} />
                    {atkT > 0.72 && (
                      <circle
                        cx={p.x + 2}
                        cy={sy}
                        r={12 + (atkT - 0.72) * 120}
                        fill="none"
                        stroke="#ff2e63"
                        strokeWidth={2.6}
                        opacity={Math.max(0, (1 - atkT) * 3.5)}
                      />
                    )}
                  </g>
                )}
              </g>
            );
          })}

          {/* Conduits from Central Reactor -> 3 Right Stations */}
          {rightStations.map((st, idx) => {
            const p = rightPos[idx];
            const sx = cx + 148;
            const sy = cy + (idx - 1) * 52;
            const ex = p.x;
            const ey = p.y + cardH / 2;
            const ctrlX = (sx + ex) / 2 - 24;
            const ctrlY = (sy + ey) / 2;
            const isActive = st.id === activeId;
            const d = `M ${sx} ${sy} Q ${ctrlX} ${ctrlY} ${ex} ${ey}`;
            const t1 = (frame * 0.022 + idx * 0.29 + 0.18) % 1;
            const t2 = (frame * 0.022 + idx * 0.29 + 0.68) % 1;
            const pt1 = quadPt([sx, sy], [ctrlX, ctrlY], [ex, ey], t1);
            const pt2 = quadPt([sx, sy], [ctrlX, ctrlY], [ex, ey], t2);
            return (
              <g key={`rc-${st.id}`}>
                <path
                  d={d}
                  fill="none"
                  stroke={st.color}
                  strokeWidth={isActive ? 4.2 : 2.6}
                  opacity={isActive ? 0.92 : 0.48}
                  filter={isActive ? "url(#cosmosGlow)" : undefined}
                />
                <path
                  d={d}
                  fill="none"
                  stroke="#ffffff"
                  strokeWidth={1.3}
                  strokeDasharray="8 14"
                  strokeDashoffset={-frame * 2.2}
                  opacity={0.75}
                />
                <circle cx={pt1.x} cy={pt1.y} r={isActive ? 8 : 6} fill="#ffffff" stroke={st.color} strokeWidth={2.5} filter="url(#cosmosGlow)" />
                <circle cx={pt2.x} cy={pt2.y} r={5} fill={st.color} filter="url(#cosmosGlow)" />
              </g>
            );
          })}

          {/* Central 3D Holographic Crypto Reactor Rings */}
          <g transform={`translate(${cx}, ${cy}) scale(${corePulse})`}>
            {/* Outer purple P2P orbit */}
            <g transform={`rotate(${rot3})`}>
              <circle r={206} fill="none" stroke="#a855f7" strokeWidth={1.8} strokeDasharray="16 14" opacity={0.52} />
            </g>
            {/* Cyan data intake ring */}
            <g transform={`rotate(${rot1})`}>
              <circle r={176} fill="none" stroke="#00f0ff" strokeWidth={2.8} strokeDasharray="48 18 12 18" opacity={0.82} filter="url(#cosmosGlow)" />
            </g>
            {/* Emerald verification ring */}
            <g transform={`rotate(${rot2})`}>
              <circle r={148} fill="none" stroke="#10ff88" strokeWidth={2.6} strokeDasharray="34 22" opacity={0.85} filter="url(#cosmosGlow)" />
            </g>
            {/* Golden Rust/RocksDB seal ring */}
            <g transform={`rotate(${rot1 * 1.4})`}>
              <circle r={120} fill="none" stroke="#ffb800" strokeWidth={3.2} strokeDasharray="64 20" opacity={0.95} filter="url(#cosmosGlow)" />
            </g>
            {/* Glowing core disc */}
            <circle r={104} fill="url(#reactorSphere)" opacity={0.28} />
            <circle r={104} fill="rgba(4,10,28,0.82)" stroke="#ffb800" strokeWidth={2} />
          </g>
        </svg>

        {/* Central Reactor Floating Typography & Badges (pulled deep into center) */}
        <div
          style={{
            position: "absolute",
            left: cx - 156,
            top: cy - 110,
            width: 312,
            height: 220,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            textAlign: "center",
            pointerEvents: "none",
          }}
        >
          <div
            style={{
              fontFamily: "Consolas, monospace",
              fontSize: 13,
              fontWeight: 900,
              color: "#ffb800",
              letterSpacing: 2.2,
              textShadow: floatTextShadow("#ffb800"),
            }}
          >
            CENTRAL ENGINE
          </div>
          <div
            style={{
              fontSize: 34,
              fontWeight: 900,
              color: "#ffffff",
              marginTop: 4,
              lineHeight: 1.08,
              textShadow: floatTextShadow("#00f0ff", true),
            }}
          >
            {c.core_title}
          </div>
          <div style={{ fontSize: 14.5, color: theme.muted, marginTop: 6, maxWidth: 230, lineHeight: 1.25 }}>
            {c.core_subtitle}
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", justifyContent: "center", marginTop: 14 }}>
            {c.core_badges.map((b, bIdx) => {
              const col = ["#ffb800", "#10ff88", "#00f0ff", "#a855f7"][bIdx % 4];
              return (
                <span
                  key={b}
                  style={{
                    padding: "4px 10px",
                    borderRadius: 999,
                    background: "rgba(3,9,26,0.94)",
                    border: `1.5px solid ${col}`,
                    fontFamily: "Consolas, monospace",
                    fontSize: 11.5,
                    fontWeight: 900,
                    color: col,
                    boxShadow: `0 6px 14px rgba(0,0,0,0.8), 0 0 14px ${col}55`,
                  }}
                >
                  {b}
                </span>
              );
            })}
          </div>
        </div>

        {/* 3 Left Inflated Stations (angled inward toward the central reactor: rotateY(+9deg)) */}
        {leftStations.map((st, idx) => {
          const p = leftPos[idx];
          const isActive = st.id === activeId;
          const s = spring({ frame: frame - (4 + idx * 6), fps, config: { damping: 165 } });
          return (
            <div
              key={st.id}
              style={{
                position: "absolute",
                left: p.x,
                top: p.y,
                width: cardW,
                height: cardH,
                opacity: s,
                transform: `rotateY(9deg) translateX(${interpolate(s, [0, 1], [-28, isActive ? 10 : 0])}px) scale(${isActive ? 1.03 : 1})`,
                transformStyle: "preserve-3d",
                borderRadius: 22,
                background: inflatedCardBg(st.color, isActive, theme.cardBg, true),
                border: `${isActive ? 2.5 : 1.5}px solid ${st.color}`,
                boxShadow: inflatedCardShadow(st.color, isActive, true),
                padding: "16px 20px",
                display: "flex",
                flexDirection: "column",
                justifyContent: "space-between",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span
                  style={{
                    fontFamily: "Consolas, monospace",
                    fontSize: 13,
                    fontWeight: 900,
                    color: st.color,
                    letterSpacing: 1.4,
                    textShadow: floatTextShadow(st.color),
                  }}
                >
                  {st.badge}
                </span>
                <span
                  style={{
                    padding: "4px 10px",
                    borderRadius: 999,
                    background: `${st.color}28`,
                    border: `1.5px solid ${st.color}`,
                    fontFamily: "Consolas, monospace",
                    fontSize: 12.5,
                    fontWeight: 900,
                    color: "#ffffff",
                    boxShadow: `0 6px 14px rgba(0,0,0,0.75), 0 0 14px ${st.color}66`,
                    transform: "translateZ(24px)",
                  }}
                >
                  {st.metric}
                </span>
              </div>
              <div
                style={{
                  fontSize: 25,
                  fontWeight: 900,
                  color: "#ffffff",
                  lineHeight: 1.12,
                  textShadow: floatTextShadow(st.color),
                  transform: "translateZ(20px)",
                }}
              >
                {st.title}
              </div>
              <div style={{ fontSize: 16, color: theme.muted, lineHeight: 1.3 }}>{st.detail}</div>
            </div>
          );
        })}

        {/* 3 Right Inflated Stations (angled inward toward the central reactor: rotateY(-9deg)) */}
        {rightStations.map((st, idx) => {
          const p = rightPos[idx];
          const isActive = st.id === activeId;
          const s = spring({ frame: frame - (10 + idx * 6), fps, config: { damping: 165 } });
          return (
            <div
              key={st.id}
              style={{
                position: "absolute",
                left: p.x,
                top: p.y,
                width: cardW,
                height: cardH,
                opacity: s,
                transform: `rotateY(-9deg) translateX(${interpolate(s, [0, 1], [28, isActive ? -10 : 0])}px) scale(${isActive ? 1.03 : 1})`,
                transformStyle: "preserve-3d",
                borderRadius: 22,
                background: inflatedCardBg(st.color, isActive, theme.cardBg, true),
                border: `${isActive ? 2.5 : 1.5}px solid ${st.color}`,
                boxShadow: inflatedCardShadow(st.color, isActive, true),
                padding: "16px 20px",
                display: "flex",
                flexDirection: "column",
                justifyContent: "space-between",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span
                  style={{
                    fontFamily: "Consolas, monospace",
                    fontSize: 13,
                    fontWeight: 900,
                    color: st.color,
                    letterSpacing: 1.4,
                    textShadow: floatTextShadow(st.color),
                  }}
                >
                  {st.badge}
                </span>
                <span
                  style={{
                    padding: "4px 10px",
                    borderRadius: 999,
                    background: `${st.color}28`,
                    border: `1.5px solid ${st.color}`,
                    fontFamily: "Consolas, monospace",
                    fontSize: 12.5,
                    fontWeight: 900,
                    color: "#ffffff",
                    boxShadow: `0 6px 14px rgba(0,0,0,0.75), 0 0 14px ${st.color}66`,
                    transform: "translateZ(24px)",
                  }}
                >
                  {st.metric}
                </span>
              </div>
              <div
                style={{
                  fontSize: 25,
                  fontWeight: 900,
                  color: "#ffffff",
                  lineHeight: 1.12,
                  textShadow: floatTextShadow(st.color),
                  transform: "translateZ(20px)",
                }}
              >
                {st.title}
              </div>
              <div style={{ fontSize: 16, color: theme.muted, lineHeight: 1.3 }}>{st.detail}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
