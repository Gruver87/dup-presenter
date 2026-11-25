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

const StoryHeading: React.FC<{
  title: string;
  subtitle?: string;
  badge?: string;
  theme: ThemePalette;
  isPortrait: boolean;
}> = ({ title, subtitle, badge, theme, isPortrait }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
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
            fontSize: isPortrait ? 44 : 50,
            fontWeight: 900,
            lineHeight: 1.06,
            letterSpacing: -0.5,
            background: `linear-gradient(90deg, ${theme.text} 0%, ${theme.accent1} 65%, ${theme.accent3} 100%)`,
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
          }}
        >
          {title}
        </div>
        {subtitle && (
          <div style={{ fontSize: isPortrait ? 20 : 22, color: theme.muted, marginTop: 6, lineHeight: 1.3 }}>
            {subtitle}
          </div>
        )}
      </div>
      {badge && (
        <div
          style={{
            padding: "8px 16px",
            borderRadius: 999,
            background: theme.cardBg,
            border: `1px solid ${theme.accent1}88`,
            fontFamily: "Consolas, monospace",
            fontSize: 14,
            fontWeight: 700,
            color: theme.accent1,
            letterSpacing: 1.4,
            whiteSpace: "nowrap",
            boxShadow: `0 0 22px ${theme.accent1}28`,
          }}
        >
          {badge}
        </div>
      )}
    </div>
  );
};

/* ============================================================================
 * 1) LEDGER_LAYERS: Isometric 3D glass-plate stack showing layered architecture
 *    ("how the ledger writes layer by layer and loses nothing").
 * ============================================================================ */
export const LedgerLayersSlide: React.FC<StorySlideProps> = ({ slide, dur, theme, isPortrait }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const layers = slide.layers ?? [];
  const count = Math.max(1, layers.length);
  const accents = [theme.accent1, theme.accent2, theme.accent3, theme.accent4, theme.accent1, theme.accent2];

  // Progress walks smoothly from top layer (0) down to persistence layer (count - 1).
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
      <div style={{ width: "100%", display: "flex", flexDirection: "column", gap: 22 }}>
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
                  borderRadius: 16,
                  background: isActive ? `${color}1c` : theme.cardBg,
                  border: `${isActive ? 2 : 1}px solid ${isActive ? color : theme.cardBorder}`,
                  boxShadow: isActive ? `0 0 28px ${color}44` : "none",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: 22, fontWeight: 800, color: isActive ? color : theme.text }}>
                    {String(idx + 1).padStart(2, "0")} · {layer.name}
                  </span>
                  <span style={{ fontSize: 13, fontFamily: "Consolas, monospace", color }}>{layer.tech}</span>
                </div>
                <div style={{ fontSize: 18, color: theme.muted, marginTop: 6 }}>{layer.desc}</div>
                <div style={{ fontSize: 16, color: theme.text, marginTop: 6, fontWeight: 600 }}>
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
  const plateW = 540;
  const plateH = 112;
  const gapY = count <= 4 ? 116 : count === 5 ? 96 : 82;
  const startTop = Math.max(24, (stageH - (count - 1) * gapY - plateH) / 2 - 14);

  return (
    <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", gap: 20 }}>
      <StoryHeading
        title={slide.title}
        subtitle={slide.subtitle}
        badge={`3D LEDGER STACK · ${count} LAYERS`}
        theme={theme}
        isPortrait={false}
      />

      <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 38 }}>
        {/* Left: Isometric 3D stack of floating glass ledger plates */}
        <div
          style={{
            width: stageW,
            height: stageH,
            position: "relative",
            perspective: 1550,
            flexShrink: 0,
          }}
        >
          {/* Ambient vertical data beam behind the stack */}
          <svg
            width={stageW}
            height={stageH}
            style={{ position: "absolute", inset: 0, overflow: "visible", pointerEvents: "none" }}
          >
            <defs>
              <linearGradient id="layerBeam" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={theme.accent1} stopOpacity="0.85" />
                <stop offset="50%" stopColor={theme.accent3} stopOpacity="0.85" />
                <stop offset="100%" stopColor={theme.accent2} stopOpacity="0.95" />
              </linearGradient>
              <filter id="layerGlow" x="-40%" y="-40%" width="180%" height="180%">
                <feGaussianBlur stdDeviation="5" result="b" />
                <feMerge>
                  <feMergeNode in="b" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>
            {/* Central spine + two side guide rails */}
            {[stageW * 0.27, stageW * 0.5, stageW * 0.73].map((cx, rIdx) => {
              const y1 = startTop + 36;
              const y2 = startTop + (count - 1) * gapY + 68;
              const pulseT = ((frame * 0.018 + rIdx * 0.33) % 1);
              const py = y1 + (y2 - y1) * pulseT;
              const pulseColor = accents[rIdx % accents.length];
              return (
                <g key={rIdx}>
                  <line
                    x1={cx}
                    y1={y1}
                    x2={cx}
                    y2={y2}
                    stroke="url(#layerBeam)"
                    strokeWidth={rIdx === 1 ? 3 : 1.5}
                    strokeDasharray={rIdx === 1 ? "none" : "6 8"}
                    opacity={rIdx === 1 ? 0.55 : 0.32}
                  />
                  <circle cx={cx} cy={py} r={rIdx === 1 ? 7 : 4.5} fill={pulseColor} filter="url(#layerGlow)" />
                </g>
              );
            })}
          </svg>

          {/* Render plates from bottom to top so upper plates sit cleanly above lower ones */}
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
            const shiftX = isActive ? 24 * activePop : 0;
            const liftY = isActive ? -8 * activePop : 0;
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
                  opacity: interpolate(entry, [0, 1], [0, isActive ? 1 : isPassed ? 0.92 : 0.68]),
                  transformStyle: "preserve-3d",
                  transform: `rotateX(${camPitch}deg) rotateZ(${camYaw}deg) translateY(${interpolate(entry, [0, 1], [34, 0])}px) scale(${isActive ? 1.04 : 1})`,
                  borderRadius: 20,
                  background: isActive
                    ? `linear-gradient(135deg, ${color}33 0%, rgba(8,22,48,0.92) 60%, ${theme.cardBg} 100%)`
                    : `linear-gradient(135deg, rgba(10,24,52,0.88) 0%, rgba(5,14,32,0.86) 100%)`,
                  border: `${isActive ? 2.5 : 1.5}px solid ${isActive ? color : isPassed ? `${color}88` : theme.cardBorder}`,
                  boxShadow: isActive
                    ? `0 12px 0 ${color}55, 0 28px 56px rgba(0,0,0,0.65), 0 0 36px ${color}55, inset 0 0 28px ${color}24`
                    : `0 9px 0 rgba(3,10,24,0.88), 0 18px 34px rgba(0,0,0,0.52)`,
                  padding: "16px 26px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
                  <div
                    style={{
                      width: 48,
                      height: 48,
                      borderRadius: 14,
                      background: isActive ? color : `${color}28`,
                      border: `1.5px solid ${color}`,
                      color: isActive ? theme.bg : color,
                      fontWeight: 900,
                      fontSize: 20,
                      fontFamily: "Consolas, monospace",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      boxShadow: isActive ? `0 0 20px ${color}` : "none",
                      flexShrink: 0,
                    }}
                  >
                    {String(idx + 1).padStart(2, "0")}
                  </div>
                  <div>
                    <div style={{ fontSize: 24, fontWeight: 900, color: theme.text, letterSpacing: 0.2 }}>
                      {layer.name}
                    </div>
                    <div
                      style={{
                        fontSize: 15,
                        fontFamily: "Consolas, monospace",
                        color,
                        marginTop: 4,
                        fontWeight: 700,
                      }}
                    >
                      {layer.tech}
                    </div>
                  </div>
                </div>
                <div
                  style={{
                    padding: "6px 12px",
                    borderRadius: 999,
                    background: isActive || isPassed ? `${color}26` : "rgba(255,255,255,0.05)",
                    border: `1px solid ${isActive || isPassed ? color : theme.cardBorder}`,
                    fontFamily: "Consolas, monospace",
                    fontSize: 13,
                    fontWeight: 800,
                    color: isActive || isPassed ? color : theme.muted,
                  }}
                >
                  {isActive ? "ACTIVE" : isPassed ? "SEALED ✓" : `L${idx + 1}`}
                </div>
              </div>
            );
          })}
        </div>

        {/* Right: Structured breakdown of every layer with active guarantee callout */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 12 }}>
          {layers.map((layer, idx) => {
            const color = layer.accent ?? accents[idx % accents.length];
            const isActive = idx === activeIdx;
            const isPassed = idx < activeIdx;
            const s = spring({ frame: frame - (8 + idx * 5), fps, config: { damping: 180 } });
            return (
              <div
                key={layer.id}
                style={{
                  opacity: interpolate(s, [0, 1], [0, isActive ? 1 : isPassed ? 0.86 : 0.62]),
                  transform: `translateX(${interpolate(s, [0, 1], [28, isActive ? -6 : 0])}px)`,
                  padding: isActive ? "16px 22px" : "12px 18px",
                  borderRadius: 16,
                  background: isActive
                    ? `linear-gradient(120deg, ${color}20 0%, ${theme.cardBg} 100%)`
                    : theme.cardBg,
                  border: `${isActive ? 2 : 1}px solid ${isActive ? color : theme.cardBorder}`,
                  boxShadow: isActive ? `0 0 30px ${color}33, 0 12px 30px rgba(0,0,0,0.36)` : "none",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span
                      style={{
                        fontFamily: "Consolas, monospace",
                        fontSize: 14,
                        fontWeight: 900,
                        color,
                      }}
                    >
                      {String(idx + 1).padStart(2, "0")}
                    </span>
                    <span style={{ fontSize: isActive ? 23 : 20, fontWeight: 800, color: theme.text }}>
                      {layer.name}
                    </span>
                  </div>
                  <span
                    style={{
                      fontSize: 13,
                      fontFamily: "Consolas, monospace",
                      color,
                      opacity: 0.92,
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
                      marginTop: 8,
                      padding: "7px 12px",
                      borderRadius: 10,
                      background: `${color}1a`,
                      borderLeft: `3px solid ${color}`,
                      fontSize: 16,
                      fontWeight: 700,
                      color: theme.text,
                    }}
                  >
                    <span style={{ color, marginRight: 8 }}>ГАРАНТИЯ:</span>
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
 * 2) TX_JOURNEY: Animated transaction lifecycle + Merkle tree folding +
 *    3D chained blocks sealing with prev_hash & RocksDB stamp.
 * ============================================================================ */
export const TxJourneySlide: React.FC<StorySlideProps> = ({ slide, dur, theme, isPortrait }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const j = slide.journey;
  if (!j) return null;

  const steps = j.steps;
  const blocks = j.blocks;
  const leaves = j.merkle_leaves ?? ["tx·a41f", "tx·9c02", "tx·e718", "TX* NEW"];
  const stepCount = Math.max(1, steps.length);
  const accents = [theme.accent1, theme.accent2, theme.accent3, theme.accent4, theme.accent1];

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
                  borderRadius: 16,
                  background: isActive ? `${color}1c` : theme.cardBg,
                  border: `${isActive ? 2 : 1}px solid ${isActive ? color : theme.cardBorder}`,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: 21, fontWeight: 800, color: isActive ? color : theme.text }}>
                    {idx + 1}. {st.title}
                  </span>
                  <span style={{ fontSize: 13, fontFamily: "Consolas, monospace", color }}>{st.badge}</span>
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
    <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", gap: 18 }}>
      <StoryHeading
        title={slide.title}
        subtitle={slide.subtitle}
        badge={`${j.tx_label}  ·  ${j.amount_label}  ·  ${j.signature_label}`}
        theme={theme}
        isPortrait={false}
      />

      {/* Middle Stage: Left = Merkle Tree Folding, Right = Chained 3D Blocks */}
      <div style={{ display: "flex", gap: 22, height: 356, alignItems: "stretch" }}>
        {/* Merkle Tree panel */}
        <div
          style={{
            width: 560,
            flexShrink: 0,
            borderRadius: 20,
            background: theme.cardBg,
            border: `1.5px solid ${merkleRootVis > 0.3 ? theme.accent3 : theme.cardBorder}`,
            boxShadow: merkleRootVis > 0.3 ? `0 0 32px ${theme.accent3}33` : "0 14px 36px rgba(0,0,0,0.4)",
            padding: "16px 20px",
            position: "relative",
            overflow: "hidden",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
            <span style={{ fontFamily: "Consolas, monospace", fontSize: 13, fontWeight: 800, color: theme.accent3, letterSpacing: 1.5 }}>
              MERKLE &amp; STATE ROOT
            </span>
            <span style={{ fontFamily: "Consolas, monospace", fontSize: 12, color: theme.muted }}>
              SHA-256 · abs_native
            </span>
          </div>

          <svg width={520} height={290} viewBox="0 0 520 262" style={{ display: "block", width: "100%", height: 290 }}>
            <defs>
              <filter id="mkGlow" x="-40%" y="-40%" width="180%" height="180%">
                <feGaussianBlur stdDeviation="3.5" result="b" />
                <feMerge>
                  <feMergeNode in="b" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>

            {/* Connecting branches: 4 leaves -> 2 pair hashes -> 1 root (exact box edges) */}
            {[
              { x1: 68, y1: 208, x2: 140, y2: 144, vis: merkleLevel1, c: theme.accent2 },
              { x1: 196, y1: 208, x2: 140, y2: 144, vis: merkleLevel1, c: theme.accent2 },
              { x1: 324, y1: 208, x2: 380, y2: 144, vis: merkleLevel1, c: theme.accent1 },
              { x1: 452, y1: 208, x2: 380, y2: 144, vis: merkleLevel1, c: theme.accent1 },
              { x1: 140, y1: 104, x2: 260, y2: 54, vis: merkleRootVis, c: theme.accent3 },
              { x1: 380, y1: 104, x2: 260, y2: 54, vis: merkleRootVis, c: theme.accent3 },
            ].map((br, i) => (
              <g key={i}>
                <line
                  x1={br.x1}
                  y1={br.y1}
                  x2={br.x2}
                  y2={br.y2}
                  stroke={br.vis > 0.1 ? br.c : "rgba(255,255,255,0.14)"}
                  strokeWidth={br.vis > 0.1 ? 2.5 : 1.5}
                  opacity={0.35 + br.vis * 0.65}
                />
                {br.vis > 0.05 && br.vis < 0.99 && (
                  <circle
                    cx={br.x1 + (br.x2 - br.x1) * br.vis}
                    cy={br.y1 + (br.y2 - br.y1) * br.vis}
                    r={5}
                    fill={br.c}
                    filter="url(#mkGlow)"
                  />
                )}
              </g>
            ))}

            {/* Root node */}
            <g opacity={0.35 + merkleRootVis * 0.65}>
              <rect
                x={126}
                y={10}
                width={268}
                height={44}
                rx={12}
                fill={merkleRootVis > 0.5 ? `${theme.accent3}33` : "rgba(10,20,42,0.88)"}
                stroke={theme.accent3}
                strokeWidth={merkleRootVis > 0.5 ? 2 : 1.2}
              />
              <text x={260} y={30} textAnchor="middle" fill={theme.accent3} fontSize={12} fontWeight={800} fontFamily="Consolas, monospace">
                MERKLE + STATE ROOT
              </text>
              <text x={260} y={46} textAnchor="middle" fill={theme.text} fontSize={12} fontFamily="Consolas, monospace">
                0x9fd8a7...b62867e
              </text>
            </g>

            {/* Pair hashes */}
            {[
              { x: 64, label: "H(tx1, tx2)", val: "0x4a8c...", c: theme.accent2 },
              { x: 304, label: "H(tx3, TX*)", val: "0x7f1e...", c: theme.accent1 },
            ].map((h, i) => (
              <g key={i} opacity={0.35 + merkleLevel1 * 0.65}>
                <rect
                  x={h.x}
                  y={104}
                  width={152}
                  height={40}
                  rx={10}
                  fill={merkleLevel1 > 0.5 ? `${h.c}24` : "rgba(10,20,42,0.84)"}
                  stroke={h.c}
                  strokeWidth={1.5}
                />
                <text x={h.x + 76} y={121} textAnchor="middle" fill={h.c} fontSize={11.5} fontWeight={800} fontFamily="Consolas, monospace">
                  {h.label}
                </text>
                <text x={h.x + 76} y={136} textAnchor="middle" fill={theme.text} fontSize={11} fontFamily="Consolas, monospace">
                  {h.val}
                </text>
              </g>
            ))}

            {/* 4 Leaf transactions */}
            {leaves.slice(0, 4).map((lf, i) => {
              const lx = 14 + i * 128;
              const isOurs = i === leaves.slice(0, 4).length - 1;
              const c = isOurs ? theme.accent1 : theme.accent2;
              return (
                <g key={i}>
                  <rect
                    x={lx}
                    y={208}
                    width={108}
                    height={42}
                    rx={10}
                    fill={isOurs ? `${theme.accent1}2e` : "rgba(10,20,42,0.84)"}
                    stroke={c}
                    strokeWidth={isOurs ? 2 : 1.2}
                  />
                  <text
                    x={lx + 54}
                    y={233}
                    textAnchor="middle"
                    fill={isOurs ? theme.accent1 : theme.text}
                    fontSize={12.5}
                    fontWeight={isOurs ? 900 : 600}
                    fontFamily="Consolas, monospace"
                  >
                    {lf}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>

        {/* Right: Live 3D Block Chain */}
        <div
          style={{
            flex: 1,
            borderRadius: 20,
            background: theme.cardBg,
            border: `1.5px solid ${blockSealed ? theme.accent1 : theme.cardBorder}`,
            boxShadow: blockSealed ? `0 0 36px ${theme.accent1}2e` : "0 14px 36px rgba(0,0,0,0.4)",
            padding: "16px 24px",
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontFamily: "Consolas, monospace", fontSize: 13, fontWeight: 800, color: theme.accent1, letterSpacing: 1.5 }}>
              IMMUTABLE BLOCK CHAIN · PREV_HASH LINKED
            </span>
            <span
              style={{
                padding: "4px 12px",
                borderRadius: 999,
                background: blockSealed ? `${theme.accent3}28` : "rgba(255,255,255,0.06)",
                border: `1px solid ${blockSealed ? theme.accent3 : theme.cardBorder}`,
                fontFamily: "Consolas, monospace",
                fontSize: 12,
                fontWeight: 800,
                color: blockSealed ? theme.accent3 : theme.muted,
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
              const borderColor = isNew
                ? blockSealed
                  ? theme.accent3
                  : theme.accent1
                : theme.accent2;
              const scale = isNew && blockSealed ? 1 + Math.sin(Math.min(1, sealSpring) * Math.PI) * 0.05 : 1;
              const pulse = ((frame * 0.03 + idx * 0.27) % 1);
              return (
                <React.Fragment key={blk.height}>
                  <div
                    style={{
                      flex: 1,
                      height: 214,
                      borderRadius: 16,
                      background: isNew && blockSealed
                        ? `linear-gradient(155deg, ${theme.accent3}2a 0%, rgba(5,18,38,0.95) 100%)`
                        : "rgba(6,18,38,0.88)",
                      border: `${isNew ? 2 : 1.5}px ${sealedNow ? "solid" : "dashed"} ${borderColor}`,
                      boxShadow: isNew && blockSealed
                        ? `0 10px 0 ${theme.accent3}44, 0 0 30px ${theme.accent3}44`
                        : `0 8px 0 rgba(2,8,20,0.9), 0 12px 26px rgba(0,0,0,0.45)`,
                      transform: `rotateY(-6deg) scale(${scale})`,
                      padding: "14px 16px",
                      display: "flex",
                      flexDirection: "column",
                      justifyContent: "space-between",
                      opacity: isNew ? (blockSealed ? 1 : 0.72 + Math.sin(frame / 7) * 0.14) : 0.94,
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontFamily: "Consolas, monospace", fontSize: 18, fontWeight: 900, color: borderColor }}>
                        {blk.height}
                      </span>
                      <span
                        style={{
                          fontSize: 11,
                          fontFamily: "Consolas, monospace",
                          fontWeight: 800,
                          color: sealedNow ? theme.accent3 : theme.accent1,
                        }}
                      >
                        {isNew ? (blockSealed ? "SEALED ✓" : "PENDING") : "FINAL"}
                      </span>
                    </div>

                    <div
                      style={{
                        padding: "8px 10px",
                        borderRadius: 10,
                        background: "rgba(255,255,255,0.04)",
                        border: `1px solid ${theme.cardBorder}`,
                        fontFamily: "Consolas, monospace",
                        fontSize: 12.5,
                        color: theme.text,
                      }}
                    >
                      <div style={{ fontSize: 10.5, color: theme.muted, marginBottom: 3 }}>BLOCK HASH</div>
                      <div>{blk.hash}</div>
                    </div>

                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, fontFamily: "Consolas, monospace", color: theme.muted }}>
                      <span>{blk.tx_count}</span>
                      <span style={{ color: borderColor }}>{isNew ? "TX* IN" : "LINKED"}</span>
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
                          stroke={idx === blocks.length - 2 && !blockSealed ? theme.accent1 : theme.accent3}
                          strokeWidth={2.5}
                          strokeDasharray={idx === blocks.length - 2 && !blockSealed ? "4 4" : "none"}
                        />
                        <circle
                          cx={4 + pulse * 36}
                          cy={13}
                          r={4}
                          fill={theme.accent1}
                        />
                      </svg>
                      <span style={{ fontSize: 10, fontFamily: "Consolas, monospace", color: theme.muted }}>
                        prev
                      </span>
                    </div>
                  )}
                </React.Fragment>
              );
            })}
          </div>
        </div>
      </div>

      {/* Bottom Stage: Animated Transaction Pipeline (packet glides across 5 steps) */}
      <div style={{ position: "relative", paddingTop: 48, display: "flex", flexDirection: "column", justifyContent: "flex-start" }}>
        {/* Rail + step anchors + traveling TX packet */}
        <svg
          width={pipeW}
          height={54}
          viewBox={`0 0 ${pipeW} 54`}
          style={{ position: "absolute", top: 6, left: 0, width: "100%", height: 54, overflow: "visible" }}
        >
          <defs>
            <linearGradient id="txRail" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor={theme.accent1} />
              <stop offset="50%" stopColor={theme.accent3} />
              <stop offset="100%" stopColor={theme.accent2} />
            </linearGradient>
            <filter id="txPktGlow" x="-40%" y="-40%" width="180%" height="180%">
              <feGaussianBlur stdDeviation="5" result="b" />
              <feMerge>
                <feMergeNode in="b" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
          <line x1={110} y1={22} x2={pipeW - 110} y2={22} stroke="rgba(255,255,255,0.14)" strokeWidth={5} strokeLinecap="round" />
          <line
            x1={110}
            y1={22}
            x2={Math.max(110, packetX)}
            y2={22}
            stroke="url(#txRail)"
            strokeWidth={5}
            strokeLinecap="round"
          />
          {steps.map((st, idx) => {
            const sx = stepCount > 1 ? 110 + ((pipeW - 220) * idx) / (stepCount - 1) : pipeW / 2;
            const c = st.accent ?? accents[idx % accents.length];
            const lit = idx <= activeStep;
            return (
              <g key={st.title}>
                <line x1={sx} y1={22} x2={sx} y2={48} stroke={lit ? c : "rgba(255,255,255,0.16)"} strokeWidth={2} />
                <circle cx={sx} cy={22} r={lit ? 6 : 4.5} fill={lit ? c : "rgba(255,255,255,0.22)"} />
              </g>
            );
          })}
          <g transform={`translate(${packetX}, 22)`}>
            <circle r={14} fill={activeColor} opacity={0.32} filter="url(#txPktGlow)" />
            <circle r={8.5} fill={activeColor} stroke={theme.text} strokeWidth={2} />
          </g>
        </svg>

        {/* Step cards */}
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
                  borderRadius: 16,
                  background: isActive
                    ? `linear-gradient(155deg, ${color}24 0%, ${theme.cardBg} 100%)`
                    : theme.cardBg,
                  border: `${isActive ? 2 : 1}px solid ${isActive ? color : isDone ? `${color}77` : theme.cardBorder}`,
                  boxShadow: isActive ? `0 0 28px ${color}40, 0 12px 26px rgba(0,0,0,0.42)` : "none",
                  transform: `translateY(${isActive ? -6 : 0}px)`,
                  opacity: isActive || isDone ? 1 : 0.66,
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "space-between",
                }}
              >
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                    <span style={{ fontFamily: "Consolas, monospace", fontSize: 13.5, fontWeight: 900, color }}>
                      0{idx + 1} · {st.badge}
                    </span>
                    {isDone && <span style={{ color: theme.accent3, fontWeight: 900, fontSize: 16 }}>✓</span>}
                  </div>
                  <div style={{ fontSize: 22, fontWeight: 800, color: theme.text, lineHeight: 1.2 }}>{st.title}</div>
                </div>
                <div style={{ fontSize: 16.5, color: theme.muted, marginTop: 8, lineHeight: 1.35 }}>{st.detail}</div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

/* ============================================================================
 * 3) MESH_NETWORK: 3D 3-node mesh topology with encrypted libp2p propagation,
 *    wire probe pulses, state alignment & failover/catch-up cards.
 * ============================================================================ */
export const MeshNetworkSlide: React.FC<StorySlideProps> = ({ slide, dur, theme, isPortrait }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const m = slide.mesh;
  if (!m) return null;

  const nodes = m.nodes;
  const recovery = m.recovery_steps;
  const accents = [theme.accent1, theme.accent3, theme.accent2, theme.accent4];
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
                borderRadius: 16,
                background: theme.cardBg,
                border: `1.5px solid ${accents[idx % accents.length]}`,
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <div>
                <div style={{ fontSize: 21, fontWeight: 800, color: theme.text }}>{n.id}</div>
                <div style={{ fontSize: 15, color: theme.muted, fontFamily: "Consolas, monospace" }}>
                  {n.role} · {n.endpoint}
                </div>
              </div>
              <span style={{ fontSize: 14, fontFamily: "Consolas, monospace", color: theme.accent3, fontWeight: 800 }}>
                {n.status}
              </span>
            </div>
          ))}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {recovery.map((r, idx) => (
            <div key={r.title} style={{ padding: "14px 18px", borderRadius: 16, background: theme.cardBg, border: `1px solid ${theme.cardBorder}` }}>
              <div style={{ fontSize: 20, fontWeight: 800, color: accents[idx % accents.length] }}>{r.title}</div>
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
  const cardW = 282;
  const cardH = 148;

  // Coordinates for 3 (triangle) or 4 (diamond) nodes inside stageW x stageH
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

  // Pairwise links between all nodes (full mesh)
  const links: Array<{ a: number; b: number }> = [];
  for (let i = 0; i < Math.min(nodes.length, coords.length); i++) {
    for (let j = i + 1; j < Math.min(nodes.length, coords.length); j++) {
      links.push({ a: i, b: j });
    }
  }

  return (
    <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", gap: 20 }}>
      <StoryHeading
        title={slide.title}
        subtitle={slide.subtitle}
        badge={`${m.protocol_label}  ·  CHAIN ${m.chain_id}`}
        theme={theme}
        isPortrait={false}
      />

      <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 36 }}>
        {/* Left: 3D Mesh Topology Stage */}
        <div
          style={{
            width: stageW,
            height: stageH,
            position: "relative",
            flexShrink: 0,
            perspective: 1500,
          }}
        >
          {/* Perspective blueprint floor */}
          <div
            style={{
              position: "absolute",
              left: 34,
              right: 34,
              top: 46,
              bottom: 24,
              borderRadius: 28,
              border: `1px solid ${theme.accent1}33`,
              background: `radial-gradient(circle at 50% 54%, ${theme.accent1}18 0%, rgba(4,14,32,0.65) 72%)`,
              backgroundImage: `linear-gradient(${theme.accent1}14 1px, transparent 1px), linear-gradient(90deg, ${theme.accent3}14 1px, transparent 1px)`,
              backgroundSize: "44px 44px",
              transform: "rotateX(22deg)",
              boxShadow: "inset 0 0 60px rgba(0,0,0,0.45), 0 30px 70px rgba(0,0,0,0.45)",
            }}
          />

          {/* Encrypted P2P links + bidirectional propagation / wire-probe pulses */}
          <svg
            width={stageW}
            height={stageH}
            style={{ position: "absolute", inset: 0, overflow: "visible", pointerEvents: "none" }}
          >
            <defs>
              <filter id="meshGlow" x="-40%" y="-40%" width="180%" height="180%">
                <feGaussianBlur stdDeviation="4.5" result="b" />
                <feMerge>
                  <feMergeNode in="b" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>
            {links.map((lk, idx) => {
              const p1 = coords[lk.a];
              const p2 = coords[lk.b];
              const fwd = (frame * 0.022 + idx * 0.31) % 1;
              const rev = (frame * 0.017 + idx * 0.43 + 0.5) % 1;
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
                    stroke={aligned ? theme.accent3 : theme.accent1}
                    strokeWidth={3}
                    opacity={0.48}
                    strokeDasharray="10 7"
                    strokeDashoffset={-frame * 1.4}
                  />
                  {/* Forward block propagation pulse */}
                  <circle cx={fx} cy={fy} r={7.5} fill={theme.accent1} filter="url(#meshGlow)" />
                  {/* Reverse wire-probe confirmation pulse */}
                  <circle cx={rx} cy={ry} r={5.5} fill={theme.accent3} filter="url(#meshGlow)" />
                </g>
              );
            })}
          </svg>

          {/* Center consensus/probe status hub */}
          <div
            style={{
              position: "absolute",
              left: stageW / 2 - 148,
              top: stageH / 2 - 34,
              width: 296,
              padding: "12px 16px",
              borderRadius: 16,
              background: "rgba(3,13,28,0.92)",
              border: `1.5px solid ${aligned ? theme.accent3 : theme.accent1}`,
              boxShadow: `0 0 32px ${aligned ? theme.accent3 : theme.accent1}44`,
              textAlign: "center",
            }}
          >
            <div style={{ fontFamily: "Consolas, monospace", fontSize: 12, fontWeight: 800, color: theme.accent1, letterSpacing: 1.4 }}>
              {m.protocol_label}
            </div>
            <div style={{ fontFamily: "Consolas, monospace", fontSize: 14, fontWeight: 900, color: theme.accent3, marginTop: 4 }}>
              {m.probe_label}
            </div>
          </div>

          {/* Node tower cards */}
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
                  borderRadius: 18,
                  background: `linear-gradient(155deg, ${color}1f 0%, rgba(5,16,36,0.95) 100%)`,
                  border: `2px solid ${color}`,
                  boxShadow: `0 10px 0 rgba(2,10,24,0.92), 0 0 28px ${color}3d`,
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
                        width: 11,
                        height: 11,
                        borderRadius: "50%",
                        background: theme.accent3,
                        boxShadow: `0 0 12px ${theme.accent3}`,
                        opacity: pulse,
                      }}
                    />
                    <span style={{ fontSize: 22, fontWeight: 900, color: theme.text }}>{node.id}</span>
                  </div>
                  <span
                    style={{
                      fontFamily: "Consolas, monospace",
                      fontSize: 12,
                      fontWeight: 800,
                      color: theme.accent3,
                      padding: "3px 9px",
                      borderRadius: 999,
                      background: `${theme.accent3}20`,
                      border: `1px solid ${theme.accent3}88`,
                    }}
                  >
                    {node.status}
                  </span>
                </div>

                <div style={{ fontSize: 16, color: theme.muted, fontWeight: 600 }}>{node.role}</div>

                <div style={{ display: "flex", justifyContent: "space-between", fontFamily: "Consolas, monospace", fontSize: 13, color }}>
                  <span>{node.endpoint}</span>
                  {node.height && <span style={{ color: theme.text }}>h={node.height}</span>}
                </div>
              </div>
            );
          })}
        </div>

        {/* Right: Sync / recovery / honesty cards */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 18 }}>
          {recovery.map((item, idx) => {
            const color = item.accent ?? accents[idx % accents.length];
            const isActive = idx === activeRecovery;
            const s = spring({ frame: frame - (12 + idx * 10), fps, config: { damping: 180 } });
            return (
              <div
                key={item.title}
                style={{
                  opacity: s,
                  transform: `translateX(${interpolate(s, [0, 1], [30, isActive ? -6 : 0])}px)`,
                  padding: "20px 24px",
                  borderRadius: 18,
                  background: isActive
                    ? `linear-gradient(125deg, ${color}20 0%, ${theme.cardBg} 100%)`
                    : theme.cardBg,
                  border: `${isActive ? 2 : 1}px solid ${isActive ? color : theme.cardBorder}`,
                  boxShadow: isActive ? `0 0 30px ${color}33, 0 14px 32px rgba(0,0,0,0.38)` : "none",
                }}
              >
                <div style={{ fontFamily: "Consolas, monospace", fontSize: 13, fontWeight: 800, color, letterSpacing: 1.5, marginBottom: 6 }}>
                  0{idx + 1} · GUARANTEE
                </div>
                <div style={{ fontSize: 25, fontWeight: 800, color: theme.text }}>{item.title}</div>
                <div style={{ fontSize: 19, color: theme.muted, marginTop: 8, lineHeight: 1.38 }}>{item.desc}</div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
