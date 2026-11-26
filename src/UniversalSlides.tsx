import React from "react";
import { AbsoluteFill, Img, Loop, Sequence, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { SceneVideo } from "./composition/sceneVideo";
import type { CinemaGrade, CinemaShot, ResolvedSlide } from "./types";
import type { ThemePalette } from "./themes";

interface UniversalSlideProps {
  slide: ResolvedSlide;
  dur: number;
  theme: ThemePalette;
  isPortrait: boolean;
  duckRatio?: number;
}

export const computeSlideLocalDuck = (
  timeSec: number,
  speechWindows: [number, number][] | undefined,
  duckRatio: number,
): number => {
  if (!speechWindows || speechWindows.length === 0 || duckRatio >= 0.999) return 1.0;
  const attack = 0.22;
  const release = 0.42;
  let maxDepth = 0;
  for (let i = 0; i < speechWindows.length; i++) {
    const [s, e] = speechWindows[i];
    if (timeSec >= s && timeSec <= e) {
      return duckRatio;
    }
    if (timeSec >= s - attack && timeSec < s) {
      const p = (timeSec - (s - attack)) / attack;
      if (p > maxDepth) maxDepth = p;
    } else if (timeSec > e && timeSec <= e + release) {
      const p = 1 - (timeSec - e) / release;
      if (p > maxDepth) maxDepth = p;
    }
  }
  return 1.0 - maxDepth * (1.0 - duckRatio);
};

const floatTextShadow = (color: string, heavy = false): string =>
  heavy
    ? `0 2px 0 #071329, 0 5px 0 #040b1a, 0 18px 28px rgba(0,0,0,0.94), 0 0 28px ${color}cc`
    : `0 2px 0 #061024, 0 4px 0 #030916, 0 12px 20px rgba(0,0,0,0.88), 0 0 18px ${color}99`;

const shelfBg = (color: string, active: boolean, baseBg: string, isQuantum: boolean): string => {
  if (!isQuantum) {
    return active ? `linear-gradient(145deg, ${color}24 0%, ${baseBg} 100%)` : baseBg;
  }
  return `radial-gradient(ellipse at 50% -10%, rgba(255,255,255,0.20) 0%, transparent 50%), radial-gradient(ellipse at 50% 118%, ${color}30 0%, transparent 56%), linear-gradient(155deg, ${color}26 0%, rgba(7,16,42,0.93) 56%, rgba(3,8,24,0.96) 100%)`;
};

const shelfShadow = (color: string, isQuantum: boolean): string =>
  isQuantum
    ? `inset 0 2px 1px rgba(255,255,255,0.34), inset 0 -10px 20px rgba(0,0,0,0.72), 0 12px 0 rgba(2,6,18,0.85), 0 24px 48px rgba(0,0,0,0.8), 0 0 34px ${color}55`
    : `0 16px 36px rgba(0,0,0,0.42), 0 0 24px ${color}28`;

const SlideHeader: React.FC<{
  title: string;
  subtitle?: string;
  badge: string;
  theme: ThemePalette;
  isPortrait: boolean;
}> = ({ title, subtitle, badge, theme, isPortrait }) => {
  const isQuantum = theme.id === "quantum_ledger";
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 20 }}>
      <div style={{ flex: 1 }}>
        <div
          style={{
            fontSize: isPortrait ? 44 : 52,
            fontWeight: 900,
            lineHeight: 1.06,
            letterSpacing: -0.9,
            color: theme.text,
            textShadow: isQuantum ? floatTextShadow(theme.accent1, true) : undefined,
          }}
        >
          {title}
        </div>
        {subtitle && (
          <div style={{ fontSize: isPortrait ? 21 : 22, color: theme.muted, marginTop: 8, lineHeight: 1.32 }}>
            {subtitle}
          </div>
        )}
      </div>
      {!isPortrait && (
        <div
          style={{
            padding: "8px 18px",
            borderRadius: 999,
            border: `1.5px solid ${theme.accent1}`,
            background: isQuantum ? "rgba(4,16,42,0.88)" : `${theme.accent1}18`,
            color: theme.accent1,
            fontFamily: "Consolas, monospace",
            fontSize: 13.5,
            fontWeight: 800,
            letterSpacing: 1.4,
            whiteSpace: "nowrap",
            boxShadow: isQuantum ? `0 0 20px ${theme.accent1}44` : undefined,
          }}
        >
          {badge}
        </div>
      )}
    </div>
  );
};

/* ============================================================================
 * 1) VERSUS_SPLIT: Side-by-side 3D comparison (A vs B) with central VS core
 *    and animated verdict banner.
 * ============================================================================ */
export const VersusSplitSlide: React.FC<UniversalSlideProps> = ({ slide, dur, theme, isPortrait }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const isQuantum = theme.id === "quantum_ledger";
  const vs = slide.versus;
  if (!vs) return null;

  const leftCol = vs.left.accent || (isQuantum ? "#ff2e63" : theme.accent4);
  const rightCol = vs.right.accent || (isQuantum ? "#10ff88" : theme.accent2);

  const leftIn = spring({ frame: Math.max(0, frame - 4), fps, config: { damping: 14, stiffness: 120 } });
  const rightIn = spring({ frame: Math.max(0, frame - 12), fps, config: { damping: 14, stiffness: 120 } });
  const vsPulse = 1 + Math.sin(frame / 14) * 0.06;
  const verdictStart = Math.max(24, Math.floor(dur * 0.55));
  const verdictIn = spring({ frame: Math.max(0, frame - verdictStart), fps, config: { damping: 15, stiffness: 110 } });

  const renderCard = (
    side: typeof vs.left,
    color: string,
    enter: number,
    rotateDeg: number,
  ) => (
    <div
      style={{
        flex: 1,
        borderRadius: 24,
        background: shelfBg(color, true, theme.cardBg, isQuantum),
        border: `2px solid ${color}`,
        boxShadow: shelfShadow(color, isQuantum),
        padding: isPortrait ? "20px 22px" : "24px 28px",
        opacity: enter,
        transform: isPortrait
          ? `translateY(${(1 - enter) * 26}px)`
          : `rotateY(${rotateDeg}deg) translateY(${(1 - enter) * 26}px)`,
        display: "flex",
        flexDirection: "column",
        gap: 14,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
        <div
          style={{
            fontSize: isPortrait ? 28 : 34,
            fontWeight: 900,
            color: "#ffffff",
            textShadow: isQuantum ? floatTextShadow(color, true) : undefined,
          }}
        >
          {side.label}
        </div>
        {side.badge && (
          <span
            style={{
              padding: "5px 12px",
              borderRadius: 999,
              border: `1.5px solid ${color}`,
              background: `${color}28`,
              color,
              fontFamily: "Consolas, monospace",
              fontSize: 13,
              fontWeight: 900,
              letterSpacing: 1.2,
            }}
          >
            {side.badge}
          </span>
        )}
      </div>

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: isPortrait ? 18 : 11,
          marginTop: 4,
          // Portrait: distribute points across the full card height instead of stacking at the top.
          flex: isPortrait ? 1 : undefined,
          justifyContent: isPortrait ? "center" : undefined,
        }}
      >
        {side.points.map((pt, idx) => {
          const itemIn = spring({
            frame: Math.max(0, frame - 16 - idx * 8),
            fps,
            config: { damping: 15, stiffness: 130 },
          });
          return (
            <div
              key={idx}
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: 12,
                padding: isPortrait ? "20px 20px" : "11px 14px",
                borderRadius: 14,
                background: "rgba(3,9,24,0.58)",
                borderLeft: `3.5px solid ${color}`,
                opacity: itemIn,
                transform: `translateX(${(1 - itemIn) * (rotateDeg > 0 ? -18 : 18)}px)`,
              }}
            >
              <span
                style={{
                  fontFamily: "Consolas, monospace",
                  fontSize: 15,
                  fontWeight: 900,
                  color,
                  marginTop: 2,
                }}
              >
                0{idx + 1}
              </span>
              <span style={{ fontSize: isPortrait ? 25 : 21, color: theme.text, lineHeight: 1.32, fontWeight: 600 }}>
                {pt}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );

  return (
    <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", gap: isPortrait ? 18 : 22 }}>
      <SlideHeader
        title={slide.title}
        subtitle={slide.subtitle}
        badge="VERSUS · A vs B"
        theme={theme}
        isPortrait={isPortrait}
      />

      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: isPortrait ? "column" : "row",
          alignItems: "center",
          gap: isPortrait ? 16 : 26,
          position: "relative",
          perspective: 1700,
        }}
      >
        {renderCard(vs.left, leftCol, leftIn, isQuantum ? 5.5 : 0)}

        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          <div
            style={{
              width: isPortrait ? 64 : 84,
              height: isPortrait ? 64 : 84,
              borderRadius: "50%",
              background: `radial-gradient(circle at 35% 30%, #ffffff 0%, ${theme.accent1} 36%, rgba(5,12,32,0.95) 85%)`,
              border: `2.5px solid ${theme.accent1}`,
              boxShadow: `0 0 36px ${theme.accent1}aa, 0 12px 26px rgba(0,0,0,0.8)`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: isPortrait ? 22 : 28,
              fontWeight: 900,
              color: "#ffffff",
              letterSpacing: 1.5,
              transform: `scale(${vsPulse})`,
              textShadow: "0 2px 12px rgba(0,0,0,0.95)",
            }}
          >
            VS
          </div>
        </div>

        {renderCard(vs.right, rightCol, rightIn, isQuantum ? -5.5 : 0)}
      </div>

      {vs.verdict && (
        <div
          style={{
            padding: "14px 22px",
            borderRadius: 18,
            background: shelfBg(theme.accent1, true, theme.cardBg, isQuantum),
            border: `2px solid ${theme.accent1}`,
            boxShadow: shelfShadow(theme.accent1, isQuantum),
            opacity: verdictIn,
            transform: `translateY(${(1 - verdictIn) * 18}px)`,
            display: "flex",
            alignItems: "center",
            gap: 14,
          }}
        >
          <span
            style={{
              padding: "4px 12px",
              borderRadius: 999,
              background: `${theme.accent1}2c`,
              border: `1px solid ${theme.accent1}`,
              color: theme.accent1,
              fontFamily: "Consolas, monospace",
              fontSize: 13.5,
              fontWeight: 900,
              letterSpacing: 1.2,
              whiteSpace: "nowrap",
            }}
          >
            VERDICT
          </span>
          <span style={{ fontSize: isPortrait ? 19 : 22, fontWeight: 700, color: "#ffffff" }}>{vs.verdict}</span>
        </div>
      )}
    </div>
  );
};

/* ============================================================================
 * 2) CHART_STORY: Animated Bar / Line / Donut charts with floating labels.
 * ============================================================================ */
export const ChartStorySlide: React.FC<UniversalSlideProps> = ({ slide, dur, theme, isPortrait }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const isQuantum = theme.id === "quantum_ledger";
  const ch = slide.chart;
  if (!ch) return null;

  const palette = [theme.accent1, theme.accent2, theme.accent3, theme.accent4, "#a855f7", "#38bdf8", "#f97316", "#22c55e"];
  const series = ch.series;
  const maxVal = Math.max(1, ...series.map((s) => s.value));
  const totalVal = Math.max(1, series.reduce((acc, s) => acc + s.value, 0));
  const grow = spring({ frame: Math.max(0, frame - 8), fps, config: { damping: 16, stiffness: 90 } });
  const sweep = interpolate(frame, [8, Math.max(36, Math.floor(dur * 0.45))], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const renderSvg = () => {
    if (ch.kind === "bar") {
      // Portrait uses a tall viewBox so the SVG fills the vertical container instead of letterboxing.
      const w = isPortrait ? 960 : 1120;
      const h = isPortrait ? 1180 : 440;
      const padL = isPortrait ? 40 : 56;
      const padB = isPortrait ? 120 : 64;
      const padT = isPortrait ? 110 : 48;
      const plotW = w - padL * 2;
      const plotH = h - padT - padB;
      const gap = isPortrait ? 36 : 24;
      const barW = Math.min(isPortrait ? 200 : 128, (plotW - gap * (series.length - 1)) / series.length);
      const startX = padL + (plotW - (barW * series.length + gap * (series.length - 1))) / 2;

      return (
        <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ width: "100%", height: "100%" }}>
          {[0.25, 0.5, 0.75, 1].map((g) => {
            const gy = padT + plotH * (1 - g);
            return <line key={g} x1={padL} y1={gy} x2={w - padL} y2={gy} stroke="rgba(255,255,255,0.10)" strokeDasharray="6 8" />;
          })}
          {series.map((pt, idx) => {
            const c = pt.color || palette[idx % palette.length];
            const itemProg = spring({ frame: Math.max(0, frame - 8 - idx * 5), fps, config: { damping: 14, stiffness: 100 } });
            const bh = Math.max(6, (pt.value / maxVal) * plotH * itemProg);
            const x = startX + idx * (barW + gap);
            const y = padT + plotH - bh;
            const valLabel = pt.display || `${pt.value}${ch.unit ? ` ${ch.unit}` : ""}`;
            return (
              <g key={pt.label}>
                <rect x={x} y={y} width={barW} height={bh} rx={14} fill={`${c}cc`} stroke={c} strokeWidth={2.4} />
                <rect x={x + 6} y={y + 4} width={Math.max(0, barW - 12)} height={Math.min(18, bh * 0.35)} rx={8} fill="rgba(255,255,255,0.28)" />
                <text x={x + barW / 2} y={y - 12} textAnchor="middle" fill="#ffffff" fontSize={isPortrait ? 38 : 22} fontWeight={900}>
                  {valLabel}
                </text>
                <text x={x + barW / 2} y={padT + plotH + 44} textAnchor="middle" fill={theme.muted} fontSize={isPortrait ? 30 : 18} fontWeight={700}>
                  {pt.label}
                </text>
              </g>
            );
          })}
        </svg>
      );
    }

    if (ch.kind === "line") {
      const w = isPortrait ? 960 : 1120;
      const h = isPortrait ? 1180 : 440;
      const padX = isPortrait ? 70 : 80;
      const padT = isPortrait ? 110 : 56;
      const padB = isPortrait ? 120 : 64;
      const plotW = w - padX * 2;
      const plotH = h - padT - padB;
      const pts = series.map((pt, idx) => {
        const x = padX + (series.length === 1 ? plotW / 2 : (idx / (series.length - 1)) * plotW);
        const y = padT + plotH - (pt.value / maxVal) * plotH;
        return { x, y, pt, c: pt.color || palette[idx % palette.length] };
      });
      const poly = pts.map((p) => `${p.x},${p.y}`).join(" ");
      const area = `${pts[0].x},${padT + plotH} ${poly} ${pts[pts.length - 1].x},${padT + plotH}`;

      return (
        <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ width: "100%", height: "100%" }}>
          <defs>
            <linearGradient id="chartAreaGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={theme.accent1} stopOpacity="0.42" />
              <stop offset="100%" stopColor={theme.accent1} stopOpacity="0.02" />
            </linearGradient>
            <clipPath id="chartReveal">
              <rect x={0} y={0} width={w * sweep} height={h} />
            </clipPath>
          </defs>
          {[0.25, 0.5, 0.75, 1].map((g) => {
            const gy = padT + plotH * (1 - g);
            return <line key={g} x1={padX} y1={gy} x2={w - padX} y2={gy} stroke="rgba(255,255,255,0.10)" strokeDasharray="6 8" />;
          })}
          <g clipPath="url(#chartReveal)">
            <polygon points={area} fill="url(#chartAreaGrad)" />
            <polyline points={poly} fill="none" stroke={theme.accent1} strokeWidth={isPortrait ? 8 : 5} strokeLinecap="round" strokeLinejoin="round" />
          </g>
          {pts.map((p, idx) => {
            const visible = sweep >= idx / Math.max(1, pts.length - 1) - 0.05;
            const valLabel = p.pt.display || `${p.pt.value}${ch.unit ? ` ${ch.unit}` : ""}`;
            return (
              <g key={p.pt.label} opacity={visible ? 1 : 0.15}>
                <circle cx={p.x} cy={p.y} r={isPortrait ? 15 : 9} fill="#ffffff" stroke={p.c} strokeWidth={isPortrait ? 6 : 4} />
                <text x={p.x} y={p.y - (isPortrait ? 28 : 18)} textAnchor="middle" fill="#ffffff" fontSize={isPortrait ? 36 : 20} fontWeight={900}>
                  {valLabel}
                </text>
                <text x={p.x} y={padT + plotH + 44} textAnchor="middle" fill={theme.muted} fontSize={isPortrait ? 30 : 18} fontWeight={700}>
                  {p.pt.label}
                </text>
              </g>
            );
          })}
        </svg>
      );
    }

    // Donut chart
    const r = 148;
    const circ = 2 * Math.PI * r;
    let offset = 0;
    return (
      <div
        style={{
          display: "flex",
          flexDirection: isPortrait ? "column" : "row",
          alignItems: "center",
          justifyContent: "center",
          gap: isPortrait ? 56 : 48,
          height: "100%",
          flexWrap: "wrap",
        }}
      >
        <svg width={isPortrait ? 620 : 380} height={isPortrait ? 620 : 380} viewBox="0 0 380 380">
          <circle cx={190} cy={190} r={r} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={44} />
          {series.map((pt, idx) => {
            const frac = pt.value / totalVal;
            const segLen = circ * frac * grow;
            const c = pt.color || palette[idx % palette.length];
            const el = (
              <circle
                key={pt.label}
                cx={190}
                cy={190}
                r={r}
                fill="none"
                stroke={c}
                strokeWidth={44}
                strokeDasharray={`${segLen} ${circ}`}
                strokeDashoffset={-offset}
                transform="rotate(-90 190 190)"
              />
            );
            offset += circ * frac;
            return el;
          })}
          <text x={190} y={184} textAnchor="middle" fill="#ffffff" fontSize={38} fontWeight={900}>
            {totalVal}
          </text>
          <text x={190} y={214} textAnchor="middle" fill={theme.muted} fontSize={16} fontWeight={700}>
            {ch.unit || "TOTAL"}
          </text>
        </svg>
        <div style={{ display: "flex", flexDirection: "column", gap: isPortrait ? 22 : 14, minWidth: isPortrait ? 760 : 320 }}>
          {series.map((pt, idx) => {
            const c = pt.color || palette[idx % palette.length];
            const pct = Math.round((pt.value / totalVal) * 100);
            return (
              <div
                key={pt.label}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  padding: "10px 16px",
                  borderRadius: 14,
                  background: "rgba(4,12,30,0.7)",
                  borderLeft: `4px solid ${c}`,
                }}
              >
                <span style={{ fontSize: isPortrait ? 30 : 20, fontWeight: 700, color: "#ffffff" }}>{pt.label}</span>
                <span style={{ fontFamily: "Consolas, monospace", fontSize: isPortrait ? 28 : 19, fontWeight: 900, color: c }}>
                  {pt.display || `${pt.value}`} ({pct}%)
                </span>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", gap: 20 }}>
      <SlideHeader
        title={slide.title}
        subtitle={slide.subtitle}
        badge={`CHART · ${ch.kind.toUpperCase()}`}
        theme={theme}
        isPortrait={isPortrait}
      />
      <div
        style={{
          flex: 1,
          borderRadius: 24,
          background: shelfBg(theme.accent1, true, theme.cardBg, isQuantum),
          border: `2px solid ${theme.accent1}`,
          boxShadow: shelfShadow(theme.accent1, isQuantum),
          padding: "20px 26px",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div style={{ flex: 1, minHeight: 0 }}>{renderSvg()}</div>
        {ch.source_note && (
          <div style={{ fontFamily: "Consolas, monospace", fontSize: 13.5, color: theme.muted, textAlign: "right", marginTop: 6 }}>
            {ch.source_note}
          </div>
        )}
      </div>
    </div>
  );
};

/* ============================================================================
 * 3) STAT_BURST: High-impact hook slide (giant floating number/thesis + rings).
 * ============================================================================ */
export const StatBurstSlide: React.FC<UniversalSlideProps> = ({ slide, theme, isPortrait }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const isQuantum = theme.id === "quantum_ledger";
  const sb = slide.stat_burst;
  if (!sb) return null;

  const pop = spring({ frame, fps, config: { damping: 11, stiffness: 140 } });
  const ringScale = 0.7 + ((frame % 60) / 60) * 0.9;
  const ringOpacity = Math.max(0, 1 - (frame % 60) / 60) * 0.62;
  const ring2Phase = ((frame + 30) % 60) / 60;
  const ring2Scale = 0.65 + ring2Phase * 0.95;
  const ring2Opacity = Math.max(0, 1 - ring2Phase) * 0.45;
  const accent = isQuantum ? theme.accent2 : theme.accent1;

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        textAlign: "center",
        position: "relative",
        gap: 22,
      }}
    >
      {/* Dual counter-phase shockwave energy rings */}
      <div
        style={{
          position: "absolute",
          width: isPortrait ? 520 : 680,
          height: isPortrait ? 520 : 680,
          borderRadius: "50%",
          border: `3px solid ${accent}`,
          opacity: ringOpacity,
          transform: `scale(${ringScale})`,
          pointerEvents: "none",
          boxShadow: `0 0 42px ${accent}`,
        }}
      />
      <div
        style={{
          position: "absolute",
          width: isPortrait ? 460 : 600,
          height: isPortrait ? 460 : 600,
          borderRadius: "50%",
          border: `2px dashed ${theme.accent1}`,
          opacity: ring2Opacity,
          transform: `scale(${ring2Scale})`,
          pointerEvents: "none",
          boxShadow: `0 0 28px ${theme.accent1}`,
        }}
      />

      {sb.kicker && (
        <div
          style={{
            padding: "8px 20px",
            borderRadius: 999,
            border: `1.5px solid ${theme.accent1}`,
            background: `${theme.accent1}22`,
            color: theme.accent1,
            fontFamily: "Consolas, monospace",
            fontSize: isPortrait ? 18 : 19,
            fontWeight: 900,
            letterSpacing: 2.2,
            textTransform: "uppercase",
          }}
        >
          {sb.kicker}
        </div>
      )}

      <div
        style={{
          fontSize: isPortrait ? 116 : 156,
          fontWeight: 900,
          lineHeight: 0.96,
          letterSpacing: -3,
          color: "#ffffff",
          transform: `scale(${0.65 + pop * 0.35})`,
          textShadow: floatTextShadow(accent, true),
          zIndex: 2,
        }}
      >
        {sb.headline}
      </div>

      <div
        style={{
          maxWidth: isPortrait ? 860 : 1180,
          fontSize: isPortrait ? 30 : 34,
          fontWeight: 700,
          color: theme.text,
          lineHeight: 1.32,
          zIndex: 2,
        }}
      >
        {sb.caption}
      </div>

      {sb.chips && sb.chips.length > 0 && (
        <div style={{ display: "flex", gap: 14, flexWrap: "wrap", justifyContent: "center", marginTop: 8, zIndex: 2 }}>
          {sb.chips.map((ch, idx) => {
            const col = ch.color || [theme.accent1, theme.accent2, theme.accent3][idx % 3];
            return (
              <span
                key={idx}
                style={{
                  padding: "10px 22px",
                  borderRadius: 999,
                  border: `1.8px solid ${col}`,
                  background: shelfBg(col, true, theme.cardBg, isQuantum),
                  color: "#ffffff",
                  fontSize: 20,
                  fontWeight: 800,
                  boxShadow: `0 8px 22px rgba(0,0,0,0.6), 0 0 20px ${col}55`,
                }}
              >
                {ch.label}
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
};

/* ============================================================================
 * 4) BROLL_CINEMATIC: Full-bleed Ken Burns visual with bold floating typography.
 * ============================================================================ */
export const BRollCinematicSlide: React.FC<UniversalSlideProps> = ({ slide, dur, theme, isPortrait }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const isQuantum = theme.id === "quantum_ledger";
  const br = slide.broll;
  if (!br) return null;

  const zoom = interpolate(frame, [0, Math.max(1, dur)], [1.0, 1.12], { extrapolateRight: "clamp" });
  const panX = interpolate(frame, [0, Math.max(1, dur)], [0, -24], { extrapolateRight: "clamp" });
  const enter = spring({ frame: Math.max(0, frame - 6), fps, config: { damping: 16, stiffness: 100 } });

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        borderRadius: 26,
        overflow: "hidden",
        position: "relative",
        border: `2px solid ${theme.accent1}`,
        boxShadow: shelfShadow(theme.accent1, isQuantum),
        display: "flex",
        flexDirection: "column",
        justifyContent: "flex-end",
        padding: isPortrait ? "34px 28px" : "44px 52px",
      }}
    >
      {br.image ? (
        <Img
          src={staticFile(br.image)}
          style={{
            position: "absolute",
            inset: 0,
            width: "100%",
            height: "100%",
            objectFit: "cover",
            transform: `scale(${zoom}) translateX(${panX}px)`,
          }}
        />
      ) : (
        <div
          style={{
            position: "absolute",
            inset: 0,
            background: `radial-gradient(ellipse at 32% 28%, ${theme.accent1}42 0%, transparent 54%), radial-gradient(ellipse at 74% 38%, ${theme.accent4}36 0%, transparent 56%), radial-gradient(ellipse at 50% 60%, ${theme.accent2}24 0%, transparent 60%), linear-gradient(145deg, #040b20 0%, #091536 55%, #020512 100%)`,
            transform: `scale(${zoom})`,
          }}
        >
          <svg width="100%" height="100%" viewBox="0 0 1600 720" preserveAspectRatio="xMidYMid slice" style={{ opacity: 0.58 }}>
            {[110, 210, 320, 440, 580].map((r, i) => (
              <ellipse
                key={r}
                cx={800}
                cy={290}
                rx={r * 1.48}
                ry={r * 0.72}
                fill="none"
                stroke={i % 2 === 0 ? theme.accent1 : theme.accent3}
                strokeWidth={1.6}
                strokeDasharray={i % 2 === 1 ? "10 12" : undefined}
                opacity={0.48 - i * 0.06}
              />
            ))}
            <line x1={120} y1={70} x2={720} y2={265} stroke={theme.accent1} strokeWidth={2.5} opacity={0.65} />
            <line x1={1480} y1={90} x2={880} y2={265} stroke={theme.accent2} strokeWidth={2.5} opacity={0.65} />
            <line x1={220} y1={520} x2={710} y2={325} stroke={theme.accent4} strokeWidth={2.2} opacity={0.55} />
            <line x1={1380} y1={510} x2={890} y2={325} stroke={theme.accent3} strokeWidth={2.2} opacity={0.55} />
            <circle cx={800} cy={290} r={42} fill={`${theme.accent1}33`} stroke={theme.accent1} strokeWidth={2} />
            <circle cx={800} cy={290} r={14} fill="#ffffff" opacity={0.85} />
          </svg>
        </div>
      )}

      {/* Cinematic vignette overlay for guaranteed typography contrast */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: "linear-gradient(180deg, rgba(2,6,18,0.22) 0%, rgba(2,6,18,0.58) 52%, rgba(2,6,18,0.94) 100%)",
        }}
      />

      {br.badge && (
        <div
          style={{
            position: "absolute",
            top: 28,
            left: 34,
            padding: "7px 16px",
            borderRadius: 999,
            background: "rgba(3,10,28,0.84)",
            border: `1.5px solid ${theme.accent1}`,
            color: theme.accent1,
            fontFamily: "Consolas, monospace",
            fontSize: 14,
            fontWeight: 900,
            letterSpacing: 1.5,
          }}
        >
          {br.badge}
        </div>
      )}

      <div style={{ position: "relative", zIndex: 2, opacity: enter, transform: `translateY(${(1 - enter) * 24}px)` }}>
        <div
          style={{
            fontSize: isPortrait ? 48 : 62,
            fontWeight: 900,
            lineHeight: 1.04,
            color: "#ffffff",
            textShadow: floatTextShadow(theme.accent1, true),
          }}
        >
          {slide.title}
        </div>
        {(br.caption || slide.subtitle) && (
          <div style={{ fontSize: isPortrait ? 23 : 26, color: "#e2e8f0", marginTop: 12, maxWidth: 1240, lineHeight: 1.34 }}>
            {br.caption || slide.subtitle}
          </div>
        )}

        {br.callouts && br.callouts.length > 0 && (
          <div style={{ display: "flex", gap: 14, marginTop: 22, flexWrap: "wrap" }}>
            {br.callouts.map((c, idx) => {
              const col = [theme.accent1, theme.accent2, theme.accent3][idx % 3];
              return (
                <div
                  key={idx}
                  style={{
                    flex: "1 1 240px",
                    padding: "13px 18px",
                    borderRadius: 16,
                    background: "rgba(4,12,30,0.82)",
                    borderLeft: `4px solid ${col}`,
                    borderTop: "1px solid rgba(255,255,255,0.16)",
                    fontSize: 19,
                    fontWeight: 700,
                    color: "#ffffff",
                  }}
                >
                  {c}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

const CINEMA_GRADE_FILTER: Record<CinemaGrade, string | undefined> = {
  none: undefined,
  cinema_warm: "contrast(1.08) saturate(1.14) sepia(0.14)",
  cinema_cold: "contrast(1.1) saturate(0.92) hue-rotate(-10deg) brightness(0.98)",
  noir: "grayscale(0.92) contrast(1.24) brightness(0.94)",
  vivid: "contrast(1.12) saturate(1.26)",
};

const inferShotKind = (src: string, explicit?: "video" | "image"): "video" | "image" => {
  if (explicit) return explicit;
  const lower = src.toLowerCase();
  if (lower.endsWith(".png") || lower.endsWith(".jpg") || lower.endsWith(".jpeg") || lower.endsWith(".webp")) {
    return "image";
  }
  return "video";
};

const CinemaLoopSegment: React.FC<{
  src: string;
  trimBefore?: number;
  srcDurationFrames?: number;
  playbackRate: number;
  muted: boolean;
  fadeInFrames: number;
  volumeFn?: (frame: number) => number;
}> = ({ src, trimBefore, srcDurationFrames, playbackRate, muted, fadeInFrames, volumeFn }) => {
  const segFrame = useCurrentFrame();
  const opacity =
    fadeInFrames > 0
      ? interpolate(segFrame, [0, fadeInFrames], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })
      : 1;
  return (
    <AbsoluteFill style={{ opacity }}>
      <SceneVideo
        src={staticFile(src)}
        trimBefore={trimBefore}
        durationInFrames={srcDurationFrames}
        playbackRate={playbackRate}
        muted={muted}
        volume={muted ? undefined : volumeFn}
        style={{ width: "100%", height: "100%", objectFit: "cover" }}
      />
    </AbsoluteFill>
  );
};

const CinemaShotLayer: React.FC<{
  shot: CinemaShot;
  slotFrom: number;
  slotDur: number;
  fadeInFrames: number;
  fadeOutAudioFrames: number;
  crossfadeFrames: number;
  loop: boolean;
  fps: number;
  speechWindows?: [number, number][];
  duckRatio: number;
}> = ({
  shot,
  slotFrom,
  slotDur,
  fadeInFrames,
  fadeOutAudioFrames,
  crossfadeFrames,
  loop,
  fps,
  speechWindows,
  duckRatio,
}) => {
  const localFrame = useCurrentFrame();
  const layerOpacity =
    fadeInFrames > 0
      ? interpolate(localFrame, [0, fadeInFrames], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })
      : 1;
  const maxZoom = typeof shot.zoom === "number" && shot.zoom >= 1.0 ? shot.zoom : 1.06;
  const scale = interpolate(localFrame, [0, Math.max(1, slotDur)], [1.0, maxZoom], { extrapolateRight: "clamp" });
  const panX =
    typeof shot.pan_x === "number"
      ? interpolate(localFrame, [0, Math.max(1, slotDur)], [0, shot.pan_x], { extrapolateRight: "clamp" })
      : 0;
  const panY =
    typeof shot.pan_y === "number"
      ? interpolate(localFrame, [0, Math.max(1, slotDur)], [0, shot.pan_y], { extrapolateRight: "clamp" })
      : 0;

  const kind = inferShotKind(shot.src, shot.kind);
  const camTransform = `scale(${scale}) translate3d(${panX}px, ${panY}px, 0)`;

  if (kind === "image") {
    return (
      <AbsoluteFill style={{ opacity: layerOpacity, overflow: "hidden" }}>
        <AbsoluteFill style={{ transform: camTransform, transformOrigin: "center center" }}>
          <Img src={staticFile(shot.src)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
        </AbsoluteFill>
      </AbsoluteFill>
    );
  }

  const rate = typeof shot.playback_rate === "number" && shot.playback_rate > 0 ? shot.playback_rate : 1.0;
  const startSec = typeof shot.start_sec === "number" && shot.start_sec > 0 ? shot.start_sec : 0;
  const trimBefore = startSec > 0 ? Math.round(startSec * fps) : undefined;
  const srcEndSec =
    typeof shot.end_sec === "number" && shot.end_sec > startSec
      ? shot.end_sec
      : typeof shot.clip_duration_sec === "number" && shot.clip_duration_sec > startSec
        ? shot.clip_duration_sec
        : 0;
  const srcSpanSec = srcEndSec > startSec ? srcEndSec - startSec : 0;
  const srcDurationFrames = srcSpanSec > 0 ? Math.max(15, Math.floor(srcSpanSec * fps)) : undefined;
  const effectivePlayFrames = srcSpanSec > 0 ? Math.max(30, Math.floor((srcSpanSec / rate) * fps)) : 0;

  const baseVol = typeof shot.audio_volume === "number" && shot.audio_volume > 0 ? shot.audio_volume : 0;
  const muted = baseVol <= 0;
  const makeVolumeFn =
    (segOffsetInSlot: number, segDur: number, segFadeIn: number, segFadeOut: number) =>
    (audioFrame: number): number => {
      const slideSec = (slotFrom + segOffsetInSlot + audioFrame) / fps;
      const duck = computeSlideLocalDuck(slideSec, speechWindows, duckRatio);
      let env = 1.0;
      if (segFadeIn > 0 && audioFrame < segFadeIn) {
        env *= Math.max(0, audioFrame / segFadeIn);
      }
      if (segFadeOut > 0 && audioFrame > segDur - segFadeOut) {
        env *= Math.max(0, (segDur - audioFrame) / segFadeOut);
      }
      return baseVol * duck * env;
    };

  const shouldLoop = loop && effectivePlayFrames > 0 && effectivePlayFrames < slotDur;
  const loopXfade = shouldLoop ? Math.min(crossfadeFrames, Math.floor(effectivePlayFrames / 3)) : 0;

  let mediaContent: React.ReactNode;
  if (shouldLoop && loopXfade > 0) {
    const step = Math.max(15, effectivePlayFrames - loopXfade);
    const segs: { from: number; dur: number; idx: number }[] = [];
    for (let from = 0, idx = 0; from < slotDur; from += step, idx++) {
      const dur = Math.min(effectivePlayFrames, slotDur - from);
      segs.push({ from, dur, idx });
      if (from + dur >= slotDur) break;
    }
    mediaContent = (
      <>
        {segs.map((seg, i) => {
          const isFirst = i === 0;
          const isLast = i === segs.length - 1;
          const segFadeIn = isFirst ? 0 : Math.min(loopXfade, Math.floor(seg.dur / 2));
          const segAudioFadeIn = isFirst ? fadeInFrames : segFadeIn;
          const segAudioFadeOut = isLast ? fadeOutAudioFrames : Math.min(loopXfade, Math.floor(seg.dur / 2));
          return (
            <Sequence key={`loop-${seg.idx}`} from={seg.from} durationInFrames={seg.dur}>
              <CinemaLoopSegment
                src={shot.src}
                trimBefore={trimBefore}
                srcDurationFrames={srcDurationFrames}
                playbackRate={rate}
                muted={muted}
                fadeInFrames={segFadeIn}
                volumeFn={muted ? undefined : makeVolumeFn(seg.from, seg.dur, segAudioFadeIn, segAudioFadeOut)}
              />
            </Sequence>
          );
        })}
      </>
    );
  } else if (shouldLoop) {
    mediaContent = (
      <Loop durationInFrames={effectivePlayFrames}>
        <SceneVideo
          src={staticFile(shot.src)}
          trimBefore={trimBefore}
          durationInFrames={srcDurationFrames}
          playbackRate={rate}
          muted={muted}
          volume={muted ? undefined : makeVolumeFn(0, effectivePlayFrames, 0, 0)}
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
      </Loop>
    );
  } else {
    mediaContent = (
      <SceneVideo
        src={staticFile(shot.src)}
        trimBefore={trimBefore}
        durationInFrames={srcDurationFrames}
        playbackRate={rate}
        muted={muted}
        volume={muted ? undefined : makeVolumeFn(0, slotDur, fadeInFrames, fadeOutAudioFrames)}
        style={{ width: "100%", height: "100%", objectFit: "cover" }}
      />
    );
  }

  return (
    <AbsoluteFill style={{ opacity: layerOpacity, overflow: "hidden" }}>
      <AbsoluteFill style={{ transform: camTransform, transformOrigin: "center center" }}>
        {mediaContent}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

export const CinemaClipSlide: React.FC<UniversalSlideProps> = ({ slide, dur, theme, isPortrait, duckRatio = 0.36 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const cc = slide.cinema || {};
  const loopEnabled = cc.loop !== false;
  const rawCrossfade = typeof cc.crossfade_frames === "number" ? Math.max(0, Math.min(30, cc.crossfade_frames)) : 12;
  const gradeFilter = CINEMA_GRADE_FILTER[cc.grade ?? "none"];
  const showLetterbox = cc.letterbox === true && !isPortrait;

  const badgeOpacity = interpolate(frame, [0, 18, Math.max(24, dur - 20), Math.max(25, dur)], [0, 0.92, 0.92, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const shots: CinemaShot[] = (() => {
    if (cc.shots && cc.shots.length > 0) {
      return cc.shots;
    }
    const singleSrc = cc.src || slide.media?.video_file;
    if (!singleSrc) return [];
    return [
      {
        src: singleSrc,
        zoom: cc.zoom,
        start_sec: cc.start_sec,
        end_sec: cc.end_sec,
        playback_rate: cc.playback_rate,
        audio_volume: cc.audio_volume,
        clip_duration_sec: cc.clip_duration_sec,
      },
    ];
  })();

  const plannedSlots = (() => {
    if (shots.length === 0) return [];
    const explicitFrames = shots.map((s) =>
      typeof s.duration_sec === "number" && s.duration_sec > 0 ? Math.max(15, Math.round(s.duration_sec * fps)) : null,
    );
    const explicitSum = explicitFrames.reduce<number>((acc, v) => acc + (v ?? 0), 0);
    const unspecifiedCount = explicitFrames.filter((v) => v === null).length;

    let baseDurs: number[];
    if (unspecifiedCount > 0) {
      const remaining = Math.max(unspecifiedCount * 15, dur - explicitSum);
      const perUnspecified = Math.max(15, Math.floor(remaining / unspecifiedCount));
      baseDurs = explicitFrames.map((v) => (v !== null ? v : perUnspecified));
    } else {
      baseDurs = explicitFrames.map((v) => v as number);
    }

    const sumBase = baseDurs.reduce((a, b) => a + b, 0);
    if (sumBase !== dur && sumBase > 0) {
      const ratio = dur / sumBase;
      baseDurs = baseDurs.map((d) => Math.max(15, Math.round(d * ratio)));
      const diff = dur - baseDurs.reduce((a, b) => a + b, 0);
      baseDurs[baseDurs.length - 1] = Math.max(15, baseDurs[baseDurs.length - 1] + diff);
    }

    const minSlot = Math.min(...baseDurs);
    const shotXfade = shots.length > 1 ? Math.min(rawCrossfade, Math.floor(minSlot / 3)) : 0;

    const starts: number[] = [];
    let cursor = 0;
    for (let i = 0; i < baseDurs.length; i++) {
      starts.push(i === 0 ? 0 : Math.max(0, cursor - Math.floor(shotXfade / 2)));
      cursor += baseDurs[i];
    }

    return shots.map((shot, i) => {
      const from = starts[i];
      const isLast = i === shots.length - 1;
      const end = isLast ? dur : Math.min(dur, starts[i + 1] + shotXfade);
      const slotDur = Math.max(1, end - from);
      return {
        shot,
        from,
        slotDur,
        fadeInFrames: i === 0 ? 0 : Math.min(shotXfade, Math.floor(slotDur / 2)),
        fadeOutAudioFrames: isLast ? 0 : Math.min(shotXfade, Math.floor(slotDur / 2)),
      };
    });
  })();

  return (
    <AbsoluteFill style={{ backgroundColor: "#000000", overflow: "hidden" }}>
      <AbsoluteFill style={gradeFilter ? { filter: gradeFilter } : undefined}>
        {plannedSlots.map((slot, idx) => (
          <Sequence key={`shot-${idx}`} from={slot.from} durationInFrames={slot.slotDur}>
            <CinemaShotLayer
              shot={slot.shot}
              slotFrom={slot.from}
              slotDur={slot.slotDur}
              fadeInFrames={slot.fadeInFrames}
              fadeOutAudioFrames={slot.fadeOutAudioFrames}
              crossfadeFrames={rawCrossfade}
              loop={loopEnabled}
              fps={fps}
              speechWindows={slide.speech_windows}
              duckRatio={duckRatio}
            />
          </Sequence>
        ))}
      </AbsoluteFill>
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(180deg, rgba(0,0,0,0.28) 0%, rgba(0,0,0,0.0) 24%, rgba(0,0,0,0.0) 68%, rgba(0,0,0,0.68) 100%)",
          pointerEvents: "none",
        }}
      />
      {showLetterbox && (
        <>
          <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: "10.5%", backgroundColor: "#000000", pointerEvents: "none" }} />
          <div style={{ position: "absolute", bottom: 0, left: 0, right: 0, height: "10.5%", backgroundColor: "#000000", pointerEvents: "none" }} />
        </>
      )}
      {cc.badge && (
        <div
          style={{
            position: "absolute",
            top: isPortrait ? 44 : showLetterbox ? 130 : 26,
            left: isPortrait ? 28 : 34,
            opacity: badgeOpacity,
            padding: "6px 14px",
            borderRadius: 999,
            background: "rgba(3,8,20,0.62)",
            border: `1px solid ${theme.accent1}88`,
            color: "#e2e8f0",
            fontFamily: "Consolas, monospace",
            fontSize: isPortrait ? 15 : 14,
            fontWeight: 700,
            letterSpacing: 1.4,
          }}
        >
          {cc.badge}
        </div>
      )}
      {slide.media?.credit && !cc.src && !(cc.shots && cc.shots.length > 0) && (
        <div
          style={{
            position: "absolute",
            right: 26,
            bottom: 18,
            fontSize: 13,
            color: "rgba(226,232,240,0.65)",
            fontFamily: "Consolas, monospace",
          }}
        >
          {slide.media.credit}
        </div>
      )}
    </AbsoluteFill>
  );
};
