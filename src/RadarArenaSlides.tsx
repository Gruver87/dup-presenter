import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { ThemePalette } from "./themes";
import { ResolvedSlide } from "./types";

const FONT_HEAD = "'Space Grotesk', 'Inter', 'Segoe UI', system-ui, sans-serif";
const FONT_MONO = "'JetBrains Mono', 'Fira Code', 'Cascadia Code', Consolas, monospace";

interface ArenaProps {
  slide: ResolvedSlide;
  dur: number;
  theme: ThemePalette;
  isPortrait: boolean;
}

const GREEN = "#00F59B";
const RED = "#FF3B5C";
const CYAN = "#00E5FF";
const AMBER = "#FFB020";
const VIOLET = "#A855F7";

interface CandlePoint {
  o: number;
  h: number;
  l: number;
  c: number;
  pct: string;
}

// Deterministic OHLC sequences (normalized 0..100 price scale)
const RUNNER_CANDLES: CandlePoint[] = [
  { o: 20, h: 24, l: 17, c: 22, pct: "+1.4%" },
  { o: 22, h: 27, l: 20, c: 25, pct: "+3.2%" },
  { o: 25, h: 28, l: 22, c: 23, pct: "+2.1%" },
  { o: 23, h: 33, l: 22, c: 31, pct: "+6.8%" },
  { o: 31, h: 40, l: 30, c: 38, pct: "+11.6%" },
  { o: 38, h: 44, l: 35, c: 42, pct: "+14.2%" },
  { o: 42, h: 46, l: 38, c: 40, pct: "+12.9%" },
  { o: 40, h: 54, l: 39, c: 52, pct: "+19.4%" },
  { o: 52, h: 63, l: 50, c: 60, pct: "+23.1%" },
  { o: 60, h: 68, l: 57, c: 66, pct: "+25.6%" },
  { o: 66, h: 78, l: 64, c: 75, pct: "+28.4%" },
  { o: 75, h: 86, l: 72, c: 84, pct: "+31.9%" },
  { o: 84, h: 90, l: 79, c: 87, pct: "+33.2%" },
  { o: 87, h: 94, l: 83, c: 91, pct: "+34.8%" },
];

// Entry at 68; hard stop -3.0% at 54; cut happens at candle index 5; candles 6..13 are post-cut crash
const CUT_CANDLES: CandlePoint[] = [
  { o: 68, h: 74, l: 66, c: 72, pct: "+1.2%" },
  { o: 72, h: 76, l: 69, c: 74, pct: "+1.8%" },
  { o: 74, h: 75, l: 65, c: 66, pct: "-0.6%" },
  { o: 66, h: 68, l: 60, c: 61, pct: "-1.9%" },
  { o: 61, h: 63, l: 56, c: 57, pct: "-2.7%" },
  { o: 57, h: 58, l: 51, c: 53, pct: "-3.0%" }, // HARD STOP TRIGGERED HERE
  { o: 53, h: 54, l: 43, c: 45, pct: "-6.4%" },
  { o: 45, h: 47, l: 36, c: 38, pct: "-9.8%" },
  { o: 38, h: 40, l: 30, c: 32, pct: "-12.4%" },
  { o: 32, h: 35, l: 25, c: 27, pct: "-14.7%" },
  { o: 27, h: 29, l: 19, c: 21, pct: "-16.9%" },
  { o: 21, h: 24, l: 15, c: 17, pct: "-18.4%" },
  { o: 17, h: 20, l: 12, c: 14, pct: "-19.6%" },
  { o: 14, h: 16, l: 9, c: 11, pct: "-21.1%" },
];

const HeaderBar: React.FC<{ title: string; badge: string; subline?: string; accent: string }> = ({
  title,
  badge,
  subline,
  accent,
}) => (
  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 18 }}>
    <div>
      <div
        style={{
          fontFamily: FONT_MONO,
          fontSize: 13,
          fontWeight: 700,
          letterSpacing: "0.14em",
          color: accent,
          textTransform: "uppercase",
          marginBottom: 4,
        }}
      >
        {badge}
      </div>
      <div
        style={{
          fontFamily: FONT_HEAD,
          fontSize: 42,
          fontWeight: 800,
          letterSpacing: "-0.02em",
          color: "#F8FAFC",
          lineHeight: 1.06,
        }}
      >
        {title}
      </div>
    </div>
    {subline ? (
      <div
        style={{
          fontFamily: FONT_MONO,
          fontSize: 14,
          color: "rgba(226,232,240,0.82)",
          padding: "7px 14px",
          borderRadius: 10,
          border: `1px solid ${accent}44`,
          background: "rgba(8,14,28,0.72)",
        }}
      >
        {subline}
      </div>
    ) : null}
  </div>
);

/* =========================================================================
   MODE 1: CORE & ARMY — Radar core + 6 army modules filtering 2,400+ pairs
   ========================================================================= */
const CoreArmyArena: React.FC<ArenaProps> = ({ slide, dur, theme }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const sweepDeg = (frame * 3.2) % 360;
  const pulse = 0.85 + 0.15 * Math.sin(frame * 0.14);

  const chaosTickers = [
    { sym: "SOL/USDT", pct: "+14.8%", ok: true, venue: "KUCOIN" },
    { sym: "PEPE2/DEX", pct: "+62.0%", ok: false, tag: "TRAP · ANTI-CHASE" },
    { sym: "SUI/USDT", pct: "+9.4%", ok: true, venue: "BINANCE" },
    { sym: "BTC-PERP", pct: "20x LEV", ok: false, tag: "FUTURES_BLOCK" },
    { sym: "NEWX/USDT", pct: "NO BOOK", ok: false, tag: "GHOST LISTING" },
    { sym: "NEAR/USDT", pct: "+7.6%", ok: true, venue: "BYBIT" },
    { sym: "RUG/USDT", pct: "-18.4%", ok: false, tag: "WIDE SPREAD" },
    { sym: "TON/USDT", pct: "+11.2%", ok: true, venue: "MEXC" },
  ];

  const armyUnits = [
    { code: "01", name: "PARALLEL INGEST", spec: "6 workers · 4 Rust WS", color: CYAN },
    { code: "02", name: "MTF ENSURE ≥85%", spec: "15m / 1h / 4h waterfall", color: GREEN },
    { code: "03", name: "RUST SCORER", spec: "radar_native · score_centi", color: VIOLET },
    { code: "04", name: "TRAP FILTER", spec: "anti-chase ≥400 bps · ghost", color: RED },
    { code: "05", name: "EQUAL SLEEVES", spec: "free USDT split by sector", color: AMBER },
    { code: "06", name: "MARK STOP GUARD", spec: "-3% cut · -5% trail · stop-only", color: GREEN },
  ];

  const allies = [
    { sym: "SOL/USDT", pct: "+14.8%", score: "84.20", mtf: "96%", setup: "BUY-WATCH" },
    { sym: "TON/USDT", pct: "+11.2%", score: "79.50", mtf: "92%", setup: "BUY-WATCH" },
    { sym: "SUI/USDT", pct: "+9.4%", score: "76.10", mtf: "91%", setup: "BUY-WATCH" },
    { sym: "NEAR/USDT", pct: "+7.6%", score: "72.80", mtf: "89%", setup: "LISTING-OK" },
  ];

  const scannedCount = Math.round(interpolate(frame, [0, Math.min(dur * 0.65, 160)], [120, 2480], { extrapolateRight: "clamp" }));

  return (
    <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", paddingBottom: 68 }}>
      <HeaderBar
        title={slide.arena?.headline || slide.title}
        badge={slide.arena?.badge || "ARENA 01 · RADAR CORE & ARMY"}
        subline={slide.arena?.subline || `SCANNED: ${scannedCount} PAIRS → TOP-10 SELECTED`}
        accent={theme.accent1 || CYAN}
      />

      <div style={{ flex: 1, display: "grid", gridTemplateColumns: "1.05fr 1.25fr 1.0fr", gap: 22, alignItems: "stretch" }}>
        {/* LEFT: MARKET CHAOS STREAM */}
        <div
          style={{
            borderRadius: 18,
            border: "1px solid rgba(255,59,92,0.35)",
            background: "linear-gradient(180deg, rgba(16,10,24,0.88), rgba(8,12,24,0.82))",
            padding: 18,
            display: "flex",
            flexDirection: "column",
            gap: 9,
            overflow: "hidden",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
            <span style={{ fontFamily: FONT_MONO, fontSize: 13, fontWeight: 700, color: RED, letterSpacing: "0.1em" }}>
              MARKET CHAOS · 6 VENUES
            </span>
            <span style={{ fontFamily: FONT_MONO, fontSize: 12, color: "rgba(248,250,252,0.7)" }}>18 MiB+ FEED</span>
          </div>
          {chaosTickers.map((t, i) => {
            const enter = spring({ frame: frame - i * 5, fps, config: { damping: 16, stiffness: 120 } });
            const driftX = !t.ok ? interpolate(frame, [i * 5 + 30, i * 5 + 70], [0, -14], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) : 0;
            return (
              <div
                key={t.sym}
                style={{
                  transform: `translateX(${(1 - enter) * -36 + driftX}px)`,
                  opacity: enter,
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  padding: "8px 12px",
                  borderRadius: 10,
                  border: `1px solid ${t.ok ? "rgba(0,245,155,0.34)" : "rgba(255,59,92,0.42)"}`,
                  background: t.ok ? "rgba(0,245,155,0.08)" : "rgba(255,59,92,0.10)",
                }}
              >
                <div>
                  <div style={{ fontFamily: FONT_MONO, fontSize: 14, fontWeight: 700, color: "#F8FAFC" }}>{t.sym}</div>
                  <div style={{ fontFamily: FONT_MONO, fontSize: 11, color: t.ok ? CYAN : RED }}>
                    {t.ok ? t.venue : t.tag}
                  </div>
                </div>
                <div
                  style={{
                    fontFamily: FONT_MONO,
                    fontSize: 15,
                    fontWeight: 800,
                    color: t.ok ? GREEN : RED,
                    padding: "3px 8px",
                    borderRadius: 6,
                    background: "rgba(0,0,0,0.35)",
                  }}
                >
                  {t.pct}
                </div>
              </div>
            );
          })}
        </div>

        {/* CENTER: RADAR CORE + 6 ARMY UNITS */}
        <div
          style={{
            borderRadius: 18,
            border: `1px solid ${CYAN}44`,
            background: "radial-gradient(circle at 50% 32%, rgba(0,229,255,0.14), rgba(6,11,24,0.92) 70%)",
            padding: 18,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "space-between",
            position: "relative",
          }}
        >
          {/* Animated Radar Scope */}
          <div style={{ position: "relative", width: 210, height: 210, display: "flex", alignItems: "center", justifyContent: "center" }}>
            <svg width={210} height={210} viewBox="0 0 210 210" style={{ position: "absolute", inset: 0 }}>
              <defs>
                <radialGradient id="radarGlow" cx="50%" cy="50%" r="50%">
                  <stop offset="0%" stopColor={CYAN} stopOpacity="0.32" />
                  <stop offset="100%" stopColor={CYAN} stopOpacity="0" />
                </radialGradient>
              </defs>
              <circle cx="105" cy="105" r="98" fill="url(#radarGlow)" stroke={`${CYAN}44`} strokeWidth="1.5" />
              <circle cx="105" cy="105" r="68" fill="none" stroke={`${CYAN}33`} strokeWidth="1" strokeDasharray="4 4" />
              <circle cx="105" cy="105" r="38" fill="none" stroke={`${GREEN}55`} strokeWidth="1.5" />
              <line x1="7" y1="105" x2="203" y2="105" stroke={`${CYAN}22`} strokeWidth="1" />
              <line x1="105" y1="7" x2="105" y2="203" stroke={`${CYAN}22`} strokeWidth="1" />
              {/* Rotating sweep wedge */}
              <g transform={`rotate(${sweepDeg} 105 105)`}>
                <path d="M105,105 L105,9 A96,96 0 0,1 182,48 Z" fill={`${GREEN}33`} />
                <line x1="105" y1="105" x2="105" y2="9" stroke={GREEN} strokeWidth="2.5" />
              </g>
              {/* Blips */}
              <circle cx="144" cy="64" r="5" fill={GREEN} opacity={pulse} />
              <circle cx="66" cy="76" r="4.5" fill={RED} opacity={0.9} />
              <circle cx="152" cy="138" r="4.5" fill={GREEN} opacity={pulse} />
              <circle cx="72" cy="146" r="4" fill={AMBER} opacity={0.85} />
            </svg>
            <div style={{ textAlign: "center", zIndex: 2 }}>
              <div style={{ fontFamily: FONT_MONO, fontSize: 11, fontWeight: 700, color: CYAN, letterSpacing: "0.14em" }}>
                RUST + PY
              </div>
              <div style={{ fontFamily: FONT_HEAD, fontSize: 21, fontWeight: 900, color: "#FFFFFF", lineHeight: 1.05 }}>
                RADAR
                <br />
                CORE
              </div>
            </div>
          </div>

          {/* 6 Army Modules Grid */}
          <div style={{ width: "100%", display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            {armyUnits.map((u, idx) => {
              const pop = spring({ frame: frame - 12 - idx * 6, fps, config: { damping: 14, stiffness: 130 } });
              return (
                <div
                  key={u.code}
                  style={{
                    transform: `scale(${0.86 + 0.14 * pop})`,
                    opacity: pop,
                    padding: "9px 11px",
                    borderRadius: 11,
                    border: `1px solid ${u.color}55`,
                    background: "rgba(9,15,30,0.86)",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontFamily: FONT_MONO, fontSize: 11, fontWeight: 800, color: u.color }}>{u.name}</span>
                    <span style={{ fontFamily: FONT_MONO, fontSize: 10, color: "rgba(255,255,255,0.45)" }}>{u.code}</span>
                  </div>
                  <div style={{ fontFamily: FONT_MONO, fontSize: 11, color: "rgba(226,232,240,0.82)", marginTop: 3 }}>
                    {u.spec}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* RIGHT: SELECTED ALLIES (TOP-N) */}
        <div
          style={{
            borderRadius: 18,
            border: `1px solid ${GREEN}55`,
            background: "linear-gradient(180deg, rgba(6,24,22,0.88), rgba(7,13,26,0.86))",
            padding: 18,
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
          }}
        >
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <span style={{ fontFamily: FONT_MONO, fontSize: 13, fontWeight: 700, color: GREEN, letterSpacing: "0.1em" }}>
                SELECTED ALLIES
              </span>
              <span
                style={{
                  fontFamily: FONT_MONO,
                  fontSize: 11,
                  fontWeight: 700,
                  color: "#052016",
                  background: GREEN,
                  padding: "3px 8px",
                  borderRadius: 6,
                }}
              >
                MTF ≥85% OK
              </span>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {allies.map((a, idx) => {
                const enter = spring({ frame: frame - 26 - idx * 8, fps, config: { damping: 14, stiffness: 115 } });
                return (
                  <div
                    key={a.sym}
                    style={{
                      transform: `translateX(${(1 - enter) * 32}px)`,
                      opacity: enter,
                      padding: "12px 14px",
                      borderRadius: 12,
                      border: `1px solid ${GREEN}66`,
                      background: "rgba(0,245,155,0.09)",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontFamily: FONT_HEAD, fontSize: 18, fontWeight: 800, color: "#FFFFFF" }}>{a.sym}</span>
                      <span style={{ fontFamily: FONT_MONO, fontSize: 18, fontWeight: 900, color: GREEN }}>{a.pct}</span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6, fontFamily: FONT_MONO, fontSize: 11 }}>
                      <span style={{ color: CYAN }}>SCORE {a.score}</span>
                      <span style={{ color: "rgba(226,232,240,0.8)" }}>MTF {a.mtf}</span>
                      <span style={{ color: GREEN, fontWeight: 700 }}>{a.setup}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div
            style={{
              marginTop: 12,
              padding: "10px 12px",
              borderRadius: 10,
              border: "1px solid rgba(255,176,32,0.45)",
              background: "rgba(255,176,32,0.09)",
              fontFamily: FONT_MONO,
              fontSize: 12,
              color: AMBER,
              textAlign: "center",
            }}
          >
            SPOT ONLY · AUTO DEFAULT OFF · DRY-RUN FIRST
          </div>
        </div>
      </div>
    </div>
  );
};

/* =========================================================================
   MODE 2: LIVE CANDLES — Green Runner vs Red Betrayer Cut at -3.0%
   ========================================================================= */
const CandleChartPanel: React.FC<{
  candles: CandlePoint[];
  revealCount: number;
  title: string;
  subtitle: string;
  accent: string;
  isCutPanel?: boolean;
  frame: number;
}> = ({ candles, revealCount, title, subtitle, accent, isCutPanel = false, frame }) => {
  const W = 780;
  const H = 370;
  const padL = 52;
  const padR = 24;
  const padT = 28;
  const padB = 34;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;
  const toY = (v: number) => padT + plotH * (1 - v / 100);
  const stepX = plotW / candles.length;
  const cutIndex = 5;
  const visibleIdx = Math.min(candles.length - 1, Math.max(0, Math.floor(revealCount) - 1));
  const currentCandle = candles[visibleIdx];
  const cutTriggered = isCutPanel && revealCount > cutIndex + 0.5;
  const trailArmed = !isCutPanel && revealCount > 5;
  const peakSoFar = !isCutPanel
    ? Math.max(...candles.slice(0, visibleIdx + 1).map((c) => c.h))
    : 76;
  const trailLevel = Math.max(20, peakSoFar - 12); // visual -5% from peak

  return (
    <div
      style={{
        borderRadius: 18,
        border: `1px solid ${accent}55`,
        background: isCutPanel
          ? "linear-gradient(180deg, rgba(28,8,18,0.88), rgba(9,12,24,0.92))"
          : "linear-gradient(180deg, rgba(6,28,22,0.88), rgba(9,12,24,0.92))",
        padding: 18,
        display: "flex",
        flexDirection: "column",
        position: "relative",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <div>
          <div style={{ fontFamily: FONT_MONO, fontSize: 12, fontWeight: 700, color: accent, letterSpacing: "0.1em" }}>
            {subtitle}
          </div>
          <div style={{ fontFamily: FONT_HEAD, fontSize: 24, fontWeight: 800, color: "#FFFFFF" }}>{title}</div>
        </div>
        <div
          style={{
            fontFamily: FONT_MONO,
            fontSize: 26,
            fontWeight: 900,
            color: isCutPanel && cutTriggered ? RED : currentCandle.c >= currentCandle.o ? GREEN : RED,
            padding: "6px 14px",
            borderRadius: 10,
            border: `1px solid ${accent}66`,
            background: "rgba(0,0,0,0.45)",
          }}
        >
          {isCutPanel && cutTriggered ? "-3.0% CUT" : currentCandle.pct}
        </div>
      </div>

      <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ flex: 1 }}>
        {/* Grid lines */}
        {[20, 40, 60, 80].map((g) => (
          <line key={g} x1={padL} y1={toY(g)} x2={W - padR} y2={toY(g)} stroke="rgba(148,163,184,0.14)" strokeWidth="1" />
        ))}

        {/* Runner: Trailing stop line */}
        {trailArmed ? (
          <g>
            <line
              x1={padL}
              y1={toY(trailLevel)}
              x2={W - padR}
              y2={toY(trailLevel)}
              stroke={CYAN}
              strokeWidth="2"
              strokeDasharray="8 6"
            />
            <rect x={padL + 8} y={toY(trailLevel) - 24} width={225} height={22} rx={6} fill="rgba(0,229,255,0.18)" stroke={CYAN} />
            <text x={padL + 18} y={toY(trailLevel) - 9} fill={CYAN} fontSize="12" fontFamily={FONT_MONO} fontWeight="700">
              TRAILING SHIELD · −5% PEAK
            </text>
          </g>
        ) : null}

        {/* Cut panel: Hard stop line at 54 (-3.0%) */}
        {isCutPanel ? (
          <g>
            <line x1={padL} y1={toY(54)} x2={W - padR} y2={toY(54)} stroke={RED} strokeWidth="2.5" strokeDasharray="8 5" />
            <rect x={padL + 8} y={toY(54) - 25} width={255} height={22} rx={6} fill="rgba(255,59,92,0.22)" stroke={RED} />
            <text x={padL + 18} y={toY(54) - 10} fill={RED} fontSize="12" fontFamily={FONT_MONO} fontWeight="700">
              HARD STOP −3.0% (KUCOIN MARK)
            </text>
          </g>
        ) : null}

        {/* Vertical laser wall when cut triggered */}
        {cutTriggered ? (
          <g>
            <line
              x1={padL + (cutIndex + 0.5) * stepX}
              y1={padT}
              x2={padL + (cutIndex + 0.5) * stepX}
              y2={H - padB}
              stroke={RED}
              strokeWidth="3"
            />
            <rect
              x={padL + (cutIndex + 0.5) * stepX + 10}
              y={padT + 8}
              width={250}
              height={46}
              rx={8}
              fill="rgba(255,59,92,0.22)"
              stroke={RED}
              strokeWidth="1.5"
            />
            <text
              x={padL + (cutIndex + 0.5) * stepX + 22}
              y={padT + 28}
              fill="#FFFFFF"
              fontSize="13"
              fontFamily={FONT_MONO}
              fontWeight="800"
            >
              CUT AT MIN LOSS (−3.0%)
            </text>
            <text
              x={padL + (cutIndex + 0.5) * stepX + 22}
              y={padT + 46}
              fill={AMBER}
              fontSize="11"
              fontFamily={FONT_MONO}
              fontWeight="700"
            >
              RE-ENTRY BAN 3h · CRASH AVOIDED
            </text>
          </g>
        ) : null}

        {/* Candles */}
        {candles.map((c, idx) => {
          const prog = interpolate(revealCount - idx, [0, 1], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          if (prog <= 0.01) return null;
          const cx = padL + (idx + 0.5) * stepX;
          const isUp = c.c >= c.o;
          const postCutGhost = isCutPanel && idx > cutIndex;
          const color = postCutGhost ? "rgba(255,59,92,0.34)" : isUp ? GREEN : RED;
          const topY = toY(Math.max(c.o, c.c));
          const botY = toY(Math.min(c.o, c.c));
          const bodyH = Math.max(4, (botY - topY) * prog);
          return (
            <g key={idx}>
              <line x1={cx} y1={toY(c.h)} x2={cx} y2={toY(c.l)} stroke={color} strokeWidth="2.5" opacity={prog} />
              <rect
                x={cx - stepX * 0.28}
                y={topY}
                width={stepX * 0.56}
                height={bodyH}
                rx={3}
                fill={color}
                stroke={postCutGhost ? RED : "none"}
                strokeDasharray={postCutGhost ? "3 2" : undefined}
              />
            </g>
          );
        })}

        {/* Pulsing active dot on current candle */}
        <circle
          cx={padL + (visibleIdx + 0.5) * stepX}
          cy={toY(currentCandle.c)}
          r={6 + 2 * Math.sin(frame * 0.25)}
          fill={isCutPanel && cutTriggered ? RED : GREEN}
          opacity={0.9}
        />
      </svg>

      <div
        style={{
          marginTop: 8,
          display: "flex",
          justifyContent: "space-between",
          fontFamily: FONT_MONO,
          fontSize: 12,
          color: "rgba(226,232,240,0.85)",
        }}
      >
        {isCutPanel ? (
          <>
            <span style={{ color: RED }}>STOP-ONLY EVEN IF DEGRADED</span>
            <span style={{ color: AMBER }}>AVOIDED DROP: −21.1%</span>
          </>
        ) : (
          <>
            <span style={{ color: GREEN }}>NO FIXED TP CAP · LET RUNNERS RUN</span>
            <span style={{ color: CYAN }}>NET OF 10 bps FEE/SIDE</span>
          </>
        )}
      </div>
    </div>
  );
};

const LiveCandlesArena: React.FC<ArenaProps> = ({ slide, dur, theme }) => {
  const frame = useCurrentFrame();
  const reveal = interpolate(frame, [8, Math.max(40, dur * 0.78)], [1, RUNNER_CANDLES.length], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", paddingBottom: 68 }}>
      <HeaderBar
        title={slide.arena?.headline || slide.title}
        badge={slide.arena?.badge || "ARENA 02 · LIVE CANDLES & DISCIPLINE"}
        subline={slide.arena?.subline || "STOP −3.0% · TRAIL −5.0% PEAK · KUCOIN MARK"}
        accent={theme.accent1 || GREEN}
      />
      <div style={{ flex: 1, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 22 }}>
        <CandleChartPanel
          candles={RUNNER_CANDLES}
          revealCount={reveal}
          title="СОЮЗНИК · RUNNER"
          subtitle="GREEN IMPULSE · TRAILING SHIELD"
          accent={GREEN}
          frame={frame}
        />
        <CandleChartPanel
          candles={CUT_CANDLES}
          revealCount={reveal}
          title="ПРЕДАТЕЛЬ · MIN-LOSS CUT"
          subtitle="RED BREAKDOWN · HARD STOP AT −3.0%"
          accent={RED}
          isCutPanel
          frame={frame}
        />
      </div>
    </div>
  );
};

/* =========================================================================
   MODE 3: TRAP GAUNTLET — 6 Market Traps shattered by 6 Fail-Closed Shields
   ========================================================================= */
const TrapGauntletArena: React.FC<ArenaProps> = ({ slide, theme }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const traps = [
    {
      icon: "⚡",
      metric: "+4.0% / 1h",
      trap: "ANTI-CHASE PUMP",
      rule: "change_bps_1h ≥ 400",
      verdict: "BUY REFUSED",
      color: AMBER,
    },
    {
      icon: "☠",
      metric: "20x USDT-M",
      trap: "FUTURES LEVERAGE",
      rule: "FUTURES_BLOCK",
      verdict: "WATCH-ONLY · NEVER AUTO",
      color: RED,
    },
    {
      icon: "◌",
      metric: "0 DEPTH",
      trap: "GHOST LISTING",
      rule: "live book join required",
      verdict: "SKIPPED",
      color: VIOLET,
    },
    {
      icon: "✕",
      metric: "MTF < 85%",
      trap: "DEGRADED SNAPSHOT",
      rule: "ok=false / mtf_ensure_ok=false",
      verdict: "0 BUYS · STOP-ONLY",
      color: RED,
    },
    {
      icon: "⏱",
      metric: "3 LOSSES",
      trap: "LOSING STREAK",
      rule: "3 losing sells in a row",
      verdict: "PAUSE BUYS 1h",
      color: AMBER,
    },
    {
      icon: "⛨",
      metric: "LATCH",
      trap: "EMERGENCY STOP",
      rule: "POST /api/trade/auto/kill",
      verdict: "INSTANT OFF + LATCH",
      color: CYAN,
    },
  ];

  const blocked = Math.min(traps.length, Math.max(0, Math.floor((frame - 8) / 14) + 1));

  return (
    <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", paddingBottom: 68 }}>
      <HeaderBar
        title={slide.arena?.headline || slide.title}
        badge={slide.arena?.badge || "ARENA 03 · TRAP GAUNTLET & SHIELDS"}
        subline={slide.arena?.subline || `TRAPS NEUTRALIZED: ${blocked} / ${traps.length} · FAIL-CLOSED`}
        accent={theme.accent1 || RED}
      />

      <div style={{ flex: 1, display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 18 }}>
        {traps.map((t, idx) => {
          const hit = spring({ frame: frame - 8 - idx * 12, fps, config: { damping: 13, stiffness: 135 } });
          return (
            <div
              key={t.trap}
              style={{
                transform: `translateY(${(1 - hit) * 26}px) scale(${0.92 + 0.08 * hit})`,
                opacity: hit,
                borderRadius: 16,
                border: `1px solid ${t.color}66`,
                background: "linear-gradient(160deg, rgba(16,14,28,0.92), rgba(7,12,24,0.9))",
                padding: 18,
                display: "flex",
                flexDirection: "column",
                justifyContent: "space-between",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div
                  style={{
                    width: 44,
                    height: 44,
                    borderRadius: 12,
                    border: `1px solid ${t.color}88`,
                    background: `${t.color}1F`,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 22,
                    color: t.color,
                  }}
                >
                  {t.icon}
                </div>
                <span
                  style={{
                    fontFamily: FONT_MONO,
                    fontSize: 16,
                    fontWeight: 900,
                    color: t.color,
                    padding: "4px 10px",
                    borderRadius: 8,
                    background: "rgba(0,0,0,0.45)",
                  }}
                >
                  {t.metric}
                </span>
              </div>

              <div style={{ marginTop: 12 }}>
                <div style={{ fontFamily: FONT_HEAD, fontSize: 20, fontWeight: 800, color: "#FFFFFF" }}>{t.trap}</div>
                <div style={{ fontFamily: FONT_MONO, fontSize: 12, color: "rgba(203,213,225,0.8)", marginTop: 4 }}>
                  {t.rule}
                </div>
              </div>

              <div
                style={{
                  marginTop: 14,
                  padding: "8px 10px",
                  borderRadius: 9,
                  background: "rgba(0,245,155,0.12)",
                  border: `1px solid ${GREEN}55`,
                  fontFamily: FONT_MONO,
                  fontSize: 12,
                  fontWeight: 800,
                  color: GREEN,
                  textAlign: "center",
                  letterSpacing: "0.06em",
                }}
              >
                SHIELD: {t.verdict}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

/* =========================================================================
   MODE 4: INTEGER VAULT — Zero Floats (i64/i128) + 4-Venue Rust WS Ring
   ========================================================================= */
const IntegerVaultArena: React.FC<ArenaProps> = ({ slide, theme }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const scales = [
    { name: "PRICE_SCALE", val: "100_000_000", note: "1e8 fixed-point i64", color: CYAN },
    { name: "QUOTE_SCALE", val: "1_000_000", note: "USDT micros · 0 float", color: GREEN },
    { name: "BASE_SCALE", val: "100_000_000", note: "1e8 base size units", color: VIOLET },
    { name: "CHANGE_BPS", val: "1 bps = 0.01%", note: "basis points integer", color: AMBER },
    { name: "SCORE_CENTI", val: "× 100", note: "Rust radar_native PyO3", color: GREEN },
  ];

  const venues = ["BINANCE WS", "BYBIT WS", "KUCOIN WS", "MEXC WS"];

  return (
    <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", paddingBottom: 68, gap: 18 }}>
      <HeaderBar
        title={slide.arena?.headline || slide.title}
        badge={slide.arena?.badge || "ARENA 04 · INTEGER VAULT & RUST ENGINE"}
        subline={slide.arena?.subline || "ZERO FLOATS ON MONEY PATHS · i64 / i128"}
        accent={theme.accent1 || CYAN}
      />

      <div style={{ display: "grid", gridTemplateColumns: "0.82fr 1.35fr", gap: 20, flex: 1 }}>
        {/* LEFT: FLOAT DRIFT REFUSED */}
        <div
          style={{
            borderRadius: 18,
            border: `1px solid ${RED}55`,
            background: "linear-gradient(180deg, rgba(32,10,18,0.88), rgba(10,12,24,0.92))",
            padding: 20,
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
          }}
        >
          <div>
            <div style={{ fontFamily: FONT_MONO, fontSize: 13, fontWeight: 700, color: RED, letterSpacing: "0.1em" }}>
              FORBIDDEN · IEEE-754 FLOAT
            </div>
            <div style={{ fontFamily: FONT_HEAD, fontSize: 28, fontWeight: 800, color: "#FFFFFF", marginTop: 6 }}>
              Float-дрейф запрещён
            </div>
            <div
              style={{
                marginTop: 18,
                padding: 16,
                borderRadius: 12,
                background: "rgba(0,0,0,0.45)",
                border: `1px solid ${RED}44`,
                fontFamily: FONT_MONO,
                fontSize: 15,
                color: RED,
                textDecoration: "line-through",
                lineHeight: 1.7,
              }}
            >
              0.1 + 0.2 = 0.30000000000000004
              <br />
              stop_price = entry * 0.97
              <br />
              qty = float(balance) / price
            </div>
          </div>
          <div
            style={{
              padding: "12px 14px",
              borderRadius: 10,
              background: "rgba(255,59,92,0.14)",
              border: `1px solid ${RED}66`,
              fontFamily: FONT_MONO,
              fontSize: 13,
              color: "#FECDD3",
            }}
          >
            В денежном контуре DUP Market Radar нет ни одного float. Только checked i64 / i128.
          </div>
        </div>

        {/* RIGHT: INTEGER SCALES + RUST WS RING */}
        <div
          style={{
            borderRadius: 18,
            border: `1px solid ${CYAN}55`,
            background: "linear-gradient(180deg, rgba(8,22,36,0.9), rgba(7,12,24,0.92))",
            padding: 20,
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
          }}
        >
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            {scales.map((s, idx) => {
              const p = spring({ frame: frame - 6 - idx * 7, fps, config: { damping: 14, stiffness: 125 } });
              return (
                <div
                  key={s.name}
                  style={{
                    transform: `scale(${0.9 + 0.1 * p})`,
                    opacity: p,
                    padding: "12px 14px",
                    borderRadius: 12,
                    border: `1px solid ${s.color}55`,
                    background: "rgba(4,10,22,0.82)",
                    gridColumn: idx === 4 ? "1 / span 2" : undefined,
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                  }}
                >
                  <div>
                    <div style={{ fontFamily: FONT_MONO, fontSize: 12, fontWeight: 700, color: s.color }}>{s.name}</div>
                    <div style={{ fontFamily: FONT_MONO, fontSize: 11, color: "rgba(203,213,225,0.75)", marginTop: 2 }}>
                      {s.note}
                    </div>
                  </div>
                  <div style={{ fontFamily: FONT_MONO, fontSize: 17, fontWeight: 900, color: "#FFFFFF" }}>{s.val}</div>
                </div>
              );
            })}
          </div>

          {/* 4-Venue Rust WS Ring strip */}
          <div
            style={{
              marginTop: 14,
              padding: "12px 14px",
              borderRadius: 12,
              border: `1px solid ${GREEN}55`,
              background: "rgba(0,245,155,0.08)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8, fontFamily: FONT_MONO, fontSize: 12 }}>
              <span style={{ color: GREEN, fontWeight: 800 }}>RUST WORKSPACE: radar_core · radar_ingest · radar_native</span>
              <span style={{ color: CYAN }}>RING 512 TICKS · 1m..4h BARS</span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
              {venues.map((v, idx) => {
                const active = Math.floor((frame + idx * 7) / 10) % 4 === idx;
                return (
                  <div
                    key={v}
                    style={{
                      padding: "7px 8px",
                      borderRadius: 8,
                      textAlign: "center",
                      fontFamily: FONT_MONO,
                      fontSize: 12,
                      fontWeight: 800,
                      color: active ? "#041612" : GREEN,
                      background: active ? GREEN : "rgba(0,245,155,0.12)",
                      border: `1px solid ${GREEN}66`,
                    }}
                  >
                    {v}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export const RadarArenaSlide: React.FC<ArenaProps> = (props) => {
  const mode = props.slide.arena?.mode ?? "core_army";
  if (mode === "live_candles") return <LiveCandlesArena {...props} />;
  if (mode === "trap_gauntlet") return <TrapGauntletArena {...props} />;
  if (mode === "integer_vault") return <IntegerVaultArena {...props} />;
  return <CoreArmyArena {...props} />;
};
