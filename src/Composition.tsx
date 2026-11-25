import React from "react";
import {
  AbsoluteFill,
  Audio,
  Freeze,
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
const IS_COSMIC = THEME.id === "cosmic_radar";
const IS_LIGHT = THEME.id === "minimal_light" || THEME.id === "paper_warm" || THEME.id === "corporate_blue";

const GRADIENT_TITLE: React.CSSProperties = {
  background: IS_COSMIC
    ? `linear-gradient(100deg, #ffffff 0%, ${CYAN} 32%, ${BLUE} 68%, ${VIOLET} 100%)`
    : `linear-gradient(95deg, ${CYAN} 0%, ${BLUE} 48%, ${VIOLET} 100%)`,
  WebkitBackgroundClip: "text",
  WebkitTextFillColor: "transparent",
};

// 3D lifted/embossed gradient title: extrusion shadow layer beneath + bright high-contrast gradient face on top
const EmbossedTitle: React.FC<{
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
const COSMIC_STARS = Array.from({ length: 92 }, (_, i) => ({
  x: ((i * 223 + 47) % Math.max(200, WIDTH)),
  y: ((i * 157 + 31) % Math.max(200, HEIGHT)),
  r: (i % 4 === 0 ? 2.4 : i % 3 === 0 ? 1.7 : 1.1),
  phase: i * 0.7,
  speed: 0.05 + (i % 5) * 0.025,
  color: i % 9 === 0 ? "#fde68a" : i % 5 === 0 ? "#bae6fd" : "#ffffff",
}));

// Selected top-100 coins orbiting the radar planet (balanced count, no clutter)
const ORBIT_COINS = [
  { sym: "BTC", icon: "₿", color: "#f7931a", rx: 1.38, ry: 0.44, tilt: -18, speed: 0.012, phase: 0.2 },
  { sym: "ETH", icon: "Ξ", color: "#818cf8", rx: 1.54, ry: 0.52, tilt: 14, speed: -0.010, phase: 1.3 },
  { sym: "SOL", icon: "◎", color: "#14f195", rx: 1.24, ry: 0.38, tilt: 28, speed: 0.015, phase: 2.4 },
  { sym: "BNB", icon: "◆", color: "#f3ba2f", rx: 1.66, ry: 0.58, tilt: -26, speed: -0.0085, phase: 3.1 },
  { sym: "XRP", icon: "✕", color: "#38bdf8", rx: 1.44, ry: 0.48, tilt: 8, speed: 0.011, phase: 4.0 },
  { sym: "HYPE", icon: "⚡", color: "#00ffd5", rx: 1.30, ry: 0.40, tilt: -34, speed: 0.016, phase: 4.9 },
  { sym: "ZEC", icon: "ⓩ", color: "#f4b728", rx: 1.74, ry: 0.60, tilt: 22, speed: -0.009, phase: 5.6 },
  { sym: "XMR", icon: "ɱ", color: "#fb923c", rx: 1.50, ry: 0.46, tilt: -10, speed: 0.013, phase: 0.9 },
  { sym: "DOGE", icon: "Ð", color: "#facc15", rx: 1.62, ry: 0.54, tilt: 32, speed: -0.011, phase: 2.0 },
  { sym: "LINK", icon: "⬡", color: "#60a5fa", rx: 1.34, ry: 0.42, tilt: -22, speed: 0.014, phase: 3.7 },
  { sym: "ADA", icon: "₳", color: "#22d3ee", rx: 1.70, ry: 0.56, tilt: 16, speed: 0.0095, phase: 5.1 },
];

// Stylised continent & city-light clusters (lat, lon in radians) projected onto the spinning globe
const EARTH_LAND_POINTS: { lat: number; lon: number; hot?: boolean }[] = (() => {
  const clusters: { latDeg: number; lonDeg: number; spreadLat: number; spreadLon: number; n: number }[] = [
    // Eurasia
    { latDeg: 48, lonDeg: 35, spreadLat: 16, spreadLon: 32, n: 26 },
    { latDeg: 36, lonDeg: 105, spreadLat: 16, spreadLon: 26, n: 22 },
    // Africa
    { latDeg: 4, lonDeg: 22, spreadLat: 24, spreadLon: 16, n: 18 },
    // North America
    { latDeg: 42, lonDeg: -98, spreadLat: 16, spreadLon: 24, n: 22 },
    // South America
    { latDeg: -18, lonDeg: -60, spreadLat: 22, spreadLon: 13, n: 16 },
    // Australia
    { latDeg: -25, lonDeg: 134, spreadLat: 10, spreadLon: 14, n: 10 },
  ];
  const pts: { lat: number; lon: number; hot?: boolean }[] = [];
  let seed = 17;
  const rand = () => {
    seed = (seed * 1664525 + 1013904223) % 4294967296;
    return seed / 4294967296;
  };
  for (const c of clusters) {
    for (let i = 0; i < c.n; i++) {
      const lat = ((c.latDeg + (rand() - 0.5) * 2 * c.spreadLat) * Math.PI) / 180;
      const lon = ((c.lonDeg + (rand() - 0.5) * 2 * c.spreadLon) * Math.PI) / 180;
      pts.push({ lat, lon, hot: i % 5 === 0 });
    }
  }
  return pts;
})();

// Compact animated candlestick + EMA mini-chart for KPI cards & Hero HUD
const CryptoMiniChart: React.FC<{
  seed?: number;
  accent?: string;
  width?: number;
  height?: number;
  bars?: number;
}> = ({ seed = 1, accent = CYAN, width = 260, height = 64, bars = 18 }) => {
  const frame = useCurrentFrame();
  const phase = frame * 0.06 + seed * 1.7;
  const candles = Array.from({ length: bars }, (_, i) => {
    const t = i * 0.55 + phase * 0.35;
    const base = 0.5 + 0.26 * Math.sin(t) + 0.12 * Math.cos(t * 2.1 + seed);
    const delta = 0.14 * Math.sin(t * 1.7 + i * 0.9 + seed);
    const open = Math.min(0.86, Math.max(0.14, base - delta * 0.5));
    const close = Math.min(0.86, Math.max(0.14, base + delta * 0.5));
    const high = Math.min(0.95, Math.max(open, close) + 0.07 + 0.04 * Math.abs(Math.sin(t * 2.7)));
    const low = Math.max(0.05, Math.min(open, close) - 0.07 - 0.04 * Math.abs(Math.cos(t * 2.3)));
    const up = close >= open;
    return { open, close, high, low, up };
  });
  const step = width / bars;
  const emaPts = candles
    .map((c, i) => `${(i * step + step * 0.5).toFixed(1)},${((1 - (c.open + c.close) * 0.5) * height).toFixed(1)}`)
    .join(" ");

  return (
    <svg width={width} height={height} style={{ display: "block", overflow: "visible" }}>
      <defs>
        <linearGradient id={`ema-${seed}`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor={accent} stopOpacity={0.3} />
          <stop offset="100%" stopColor={accent} stopOpacity={1} />
        </linearGradient>
      </defs>
      {candles.map((c, i) => {
        const cx = i * step + step * 0.5;
        const yHigh = (1 - c.high) * height;
        const yLow = (1 - c.low) * height;
        const yTop = (1 - Math.max(c.open, c.close)) * height;
        const bodyH = Math.max(3, Math.abs(c.close - c.open) * height);
        const col = c.up ? "#00ffd5" : "#f43f5e";
        return (
          <g key={i}>
            <line x1={cx} y1={yHigh} x2={cx} y2={yLow} stroke={col} strokeWidth={1.4} strokeOpacity={0.75} />
            <rect
              x={cx - step * 0.28}
              y={yTop}
              width={Math.max(4, step * 0.56)}
              height={bodyH}
              rx={1.5}
              fill={col}
              fillOpacity={0.86}
            />
          </g>
        );
      })}
      <polyline points={emaPts} fill="none" stroke={`url(#ema-${seed})`} strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
};

// Packet flow: four exchange feeds stream into the Rust scoring core at the planet centre (cosmic theme only).
const EXCHANGE_NODES: { name: string; x: number; y: number; color: string }[] = [
  { name: "Binance", x: 0.4, y: 0.08, color: "#facc15" },
  { name: "Bybit", x: 0.66, y: 0.08, color: "#fb923c" },
  { name: "KuCoin", x: 0.4, y: 0.83, color: "#00ffd5" },
  { name: "MEXC", x: 0.66, y: 0.83, color: "#38bdf8" },
];

const ExchangeFlowLayer: React.FC<{ cx: number; cy: number }> = ({ cx, cy }) => {
  const frame = useCurrentFrame();
  const paths = EXCHANGE_NODES.map((node, idx) => {
    const ax = node.x * WIDTH;
    const ay = node.y * HEIGHT;
    const mx = (ax + cx) / 2;
    const my = (ay + cy) / 2;
    const dx = cx - ax;
    const dy = cy - ay;
    const len = Math.hypot(dx, dy) || 1;
    // Bow the feed toward the middle of the frame so the paths read as a curved data bus.
    const bend = 0.22 * len;
    const qx = mx - (dy / len) * bend;
    const qy = my + (dx / len) * bend;
    const point = (t: number) => ({
      x: (1 - t) * (1 - t) * ax + 2 * (1 - t) * t * qx + t * t * cx,
      y: (1 - t) * (1 - t) * ay + 2 * (1 - t) * t * qy + t * t * cy,
    });
    const packets = [0, 1 / 3, 2 / 3].map((k) => {
      const t = (frame * 0.011 + k + idx * 0.19) % 1;
      const p = point(t);
      // Fade in at the exchange and out just before reaching the sphere
      const alpha = Math.min(1, t / 0.12) * Math.min(1, (0.94 - t) / 0.18);
      return { ...p, alpha: Math.max(0, alpha) };
    });
    return { node, ax, ay, qx, qy, cx, cy, packets };
  });

  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      <svg width={WIDTH} height={HEIGHT} style={{ position: "absolute", inset: 0 }}>
        {paths.map(({ node, ax, ay, qx, qy, packets }) => (
          <g key={node.name}>
            <path
              d={`M ${ax} ${ay} Q ${qx} ${qy} ${cx} ${cy}`}
              fill="none"
              stroke={node.color}
              strokeWidth={1.8}
              strokeOpacity={0.36}
              strokeDasharray="5 8"
            />
            {packets.map((p, k) => (
              <g key={k}>
                <circle cx={p.x} cy={p.y} r={11} fill={node.color} fillOpacity={0.28 * p.alpha} />
                <circle cx={p.x} cy={p.y} r={4.2} fill="#ffffff" fillOpacity={0.96 * p.alpha} />
              </g>
            ))}
            <circle cx={ax} cy={ay} r={6.5} fill={node.color} fillOpacity={0.95} />
            <text
              x={ax}
              y={ay - 14}
              textAnchor="middle"
              fill={node.color}
              fillOpacity={0.95}
              fontFamily="Consolas, monospace"
              fontSize={15}
              fontWeight={800}
              letterSpacing={1.4}
            >
              {node.name.toUpperCase()}
            </text>
          </g>
        ))}
      </svg>
    </AbsoluteFill>
  );
};

// KPI values like "4 488", "~150 мс", "0 float" count up from zero. Values with decimals or ranges stay static.
const parseKpiValue = (raw: string): { prefix: string; num: number; suffix: string; grouped: boolean } | null => {
  if (/[.,/–-]\d/.test(raw)) return null;
  const m = raw.match(/^(\D*?)(\d[\d ]*\d|\d)(\D*)$/);
  if (!m) return null;
  const digits = m[2].replace(/ /g, "");
  const num = Number(digits);
  if (!Number.isFinite(num)) return null;
  return { prefix: m[1], num, suffix: m[3], grouped: num >= 1000 };
};

const AnimatedKpiValue: React.FC<{ value: string; startFrame: number; durationFrames?: number }> = ({
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
const CosmicEarthRadarLayer: React.FC = () => {
  const frame = useCurrentFrame();
  const cx = IS_PORTRAIT ? WIDTH * 0.5 : WIDTH * 0.52;
  const cy = IS_PORTRAIT ? HEIGHT * 0.50 : HEIGHT * 0.52;
  const R = IS_PORTRAIT ? 215 : 270;
  const spin = frame * 0.011;
  const sweepDeg = (frame * 1.9) % 360;

  // Project spinning meridians
  const meridians = Array.from({ length: 12 }, (_, m) => {
    const lon = (m / 12) * Math.PI * 2 + spin;
    const pts: string[] = [];
    for (let s = -12; s <= 12; s++) {
      const lat = (s / 12) * (Math.PI * 0.48);
      const z = Math.cos(lat) * Math.cos(lon);
      if (z >= -0.05) {
        const x = cx + R * Math.cos(lat) * Math.sin(lon);
        const y = cy - R * Math.sin(lat);
        pts.push(`${x.toFixed(1)},${y.toFixed(1)}`);
      }
    }
    return pts.join(" ");
  });

  // Project spinning continent lights on front hemisphere
  const visibleLights = EARTH_LAND_POINTS.map((p, idx) => {
    const lon = p.lon + spin;
    const z = Math.cos(p.lat) * Math.cos(lon);
    if (z <= 0.04) return null;
    const x = cx + R * Math.cos(p.lat) * Math.sin(lon);
    const y = cy - R * Math.sin(p.lat);
    // Radar sweep highlight when beam passes over this point's angle
    const ang = ((Math.atan2(y - cy, x - cx) * 180) / Math.PI + 360) % 360;
    const diff = (sweepDeg - ang + 360) % 360;
    const ping = diff < 32 ? 1 - diff / 32 : 0;
    return { idx, x, y, z, hot: p.hot, ping };
  }).filter((v): v is { idx: number; x: number; y: number; z: number; hot: boolean | undefined; ping: number } => v !== null);

  // Orbiting Top-100 coins split into back (behind Earth) and front (in front of Earth)
  const projectedCoins = ORBIT_COINS.map((c) => {
    const a = frame * c.speed + c.phase;
    const ox = Math.cos(a) * R * c.rx;
    const oy = Math.sin(a) * R * c.ry;
    const z = Math.sin(a); // -1 = far behind planet, +1 = close in front
    const rad = (c.tilt * Math.PI) / 180;
    const rx = ox * Math.cos(rad) - oy * Math.sin(rad);
    const ry = ox * Math.sin(rad) + oy * Math.cos(rad);
    const scale = 0.72 + (z + 1) * 0.24;
    const opacity = 0.32 + (z + 1) * 0.34;
    return { ...c, x: cx + rx, y: cy + ry, z, scale, opacity };
  });

  const backCoins = projectedCoins.filter((c) => c.z < 0);
  const frontCoins = projectedCoins.filter((c) => c.z >= 0);

  // Background holographic candlestick wave along lower third
  const bgBars = IS_PORTRAIT ? 28 : 48;
  const bgStep = WIDTH / bgBars;
  const bgCandles = Array.from({ length: bgBars }, (_, i) => {
    const t = i * 0.38 + frame * 0.025;
    const mid = 0.5 + 0.24 * Math.sin(t) + 0.14 * Math.cos(t * 1.9);
    const d = 0.12 * Math.sin(t * 2.3 + i);
    const o = mid - d * 0.5;
    const c = mid + d * 0.5;
    const h = Math.max(o, c) + 0.07;
    const l = Math.min(o, c) - 0.07;
    return { i, o, c, h, l, up: c >= o };
  });
  const chartTop = HEIGHT - (IS_PORTRAIT ? 340 : 250);
  const chartH = IS_PORTRAIT ? 180 : 155;

  const renderCoin = (c: (typeof projectedCoins)[number]) => (
    <div
      key={c.sym}
      style={{
        position: "absolute",
        left: c.x,
        top: c.y,
        transform: `translate(-50%, -50%) scale(${c.scale.toFixed(3)})`,
        opacity: c.opacity,
        display: "flex",
        alignItems: "center",
        gap: 7,
        padding: "5px 12px 5px 7px",
        borderRadius: 999,
        background: "rgba(4, 10, 28, 0.82)",
        border: `1.5px solid ${c.color}cc`,
        boxShadow: `0 0 18px ${c.color}55, 0 8px 20px rgba(0,0,0,0.6)`,
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          width: 24,
          height: 24,
          borderRadius: "50%",
          background: `radial-gradient(circle at 30% 30%, #ffffff, ${c.color} 55%, ${c.color}aa 100%)`,
          color: "#020512",
          fontWeight: 900,
          fontSize: 13,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          boxShadow: `0 0 10px ${c.color}`,
        }}
      >
        {c.icon}
      </div>
      <span
        style={{
          fontFamily: "Consolas, 'Cascadia Code', monospace",
          fontSize: 13,
          fontWeight: 800,
          letterSpacing: 1,
          color: "#ffffff",
          textShadow: `0 0 8px ${c.color}`,
        }}
      >
        {c.sym}
      </span>
    </div>
  );

  return (
    <AbsoluteFill style={{ pointerEvents: "none", overflow: "hidden" }}>
      {/* Deep-space starfield with twinkling */}
      <svg width={WIDTH} height={HEIGHT} style={{ position: "absolute", inset: 0 }}>
        {COSMIC_STARS.map((st, idx) => {
          const tw = 0.35 + 0.65 * Math.abs(Math.sin(frame * st.speed + st.phase));
          const sx = (st.x + frame * 0.08 * (idx % 3 === 0 ? 1.4 : 0.6)) % WIDTH;
          return (
            <circle
              key={idx}
              cx={sx}
              cy={st.y}
              r={st.r}
              fill={st.color}
              fillOpacity={tw * 0.85}
            />
          );
        })}

        {/* Holographic candlestick chart ribbon across lower background */}
        <g opacity={0.34}>
          {bgCandles.map((bc) => {
            const x = bc.i * bgStep + bgStep * 0.5;
            const yH = chartTop + (1 - bc.h) * chartH;
            const yL = chartTop + (1 - bc.l) * chartH;
            const yT = chartTop + (1 - Math.max(bc.o, bc.c)) * chartH;
            const bH = Math.max(4, Math.abs(bc.c - bc.o) * chartH);
            const col = bc.up ? "#00ffd5" : "#f43f5e";
            return (
              <g key={bc.i}>
                <line x1={x} y1={yH} x2={x} y2={yL} stroke={col} strokeWidth={1.7} />
                <rect x={x - bgStep * 0.24} y={yT} width={bgStep * 0.48} height={bH} rx={2} fill={col} />
              </g>
            );
          })}
          <polyline
            points={bgCandles
              .map((bc) => `${(bc.i * bgStep + bgStep * 0.5).toFixed(1)},${(chartTop + (1 - (bc.o + bc.c) * 0.5) * chartH).toFixed(1)}`)
              .join(" ")}
            fill="none"
            stroke="#fbbf24"
            strokeWidth={2.6}
          />
        </g>
      </svg>

      {/* Exchange feeds streaming into the Rust core at the planet centre */}
      <ExchangeFlowLayer cx={cx} cy={cy} />

      {/* Coins passing behind the planet */}
      {backCoins.map(renderCoin)}

      {/* Spinning 3D Earth-Radar sphere */}
      <svg width={WIDTH} height={HEIGHT} style={{ position: "absolute", inset: 0, opacity: 0.84 }}>
        <defs>
          <radialGradient id="earthOcean" cx="35%" cy="32%" r="68%">
            <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.92} />
            <stop offset="38%" stopColor="#1d4ed8" stopOpacity={0.94} />
            <stop offset="76%" stopColor="#1e1b4b" stopOpacity={0.96} />
            <stop offset="100%" stopColor="#03071a" stopOpacity={0.98} />
          </radialGradient>
          <radialGradient id="earthAtmo" cx="50%" cy="50%" r="50%">
            <stop offset="72%" stopColor="#00ffd5" stopOpacity={0} />
            <stop offset="90%" stopColor="#38bdf8" stopOpacity={0.52} />
            <stop offset="100%" stopColor="#c084fc" stopOpacity={0} />
          </radialGradient>
          <linearGradient id="anamorphicFlare" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#00ffd5" stopOpacity={0} />
            <stop offset="50%" stopColor="#bae6fd" stopOpacity={0.65} />
            <stop offset="100%" stopColor="#c084fc" stopOpacity={0} />
          </linearGradient>
          <clipPath id="earthClip">
            <circle cx={cx} cy={cy} r={R} />
          </clipPath>
        </defs>

        {/* Outer orbital radar rings around the planet */}
        {[1.18, 1.42, 1.68].map((mult, idx) => (
          <ellipse
            key={idx}
            cx={cx}
            cy={cy}
            rx={R * mult}
            ry={R * mult * 0.36}
            fill="none"
            stroke={[CYAN, BLUE, VIOLET][idx]}
            strokeWidth={idx === 0 ? 1.6 : 1.1}
            strokeDasharray={idx === 1 ? "8 10" : undefined}
            strokeOpacity={0.42 - idx * 0.08}
            transform={`rotate(${idx === 0 ? -16 : idx === 1 ? 14 : -8} ${cx} ${cy})`}
          />
        ))}

        {/* Atmosphere halo */}
        <circle cx={cx} cy={cy} r={R * 1.16} fill="url(#earthAtmo)" />

        {/* Planet sphere */}
        <circle cx={cx} cy={cy} r={R} fill="url(#earthOcean)" stroke="#38bdf8" strokeWidth={2} strokeOpacity={0.65} />

        {/* Spinning latitude & longitude wireframe + continent city lights clipped to sphere */}
        <g clipPath="url(#earthClip)">
          {[-0.6, -0.3, 0, 0.3, 0.6].map((latFrac, idx) => {
            const ly = cy - R * latFrac;
            const lr = R * Math.sqrt(Math.max(0.01, 1 - latFrac * latFrac));
            return (
              <ellipse
                key={idx}
                cx={cx}
                cy={ly}
                rx={lr}
                ry={lr * 0.12}
                fill="none"
                stroke="#38bdf8"
                strokeWidth={0.9}
                strokeOpacity={0.28}
              />
            );
          })}
          {meridians.map((pts, idx) => (
            <polyline key={idx} points={pts} fill="none" stroke="#00ffd5" strokeWidth={0.95} strokeOpacity={0.26} />
          ))}

          {/* Spinning continent lights & radar ping flashes */}
          {visibleLights.map((p) => {
            const baseCol = p.hot ? "#fbbf24" : "#00ffd5";
            const r = (p.hot ? 3.2 : 2.1) + p.ping * 3.5;
            return (
              <g key={p.idx}>
                {p.ping > 0.2 && (
                  <circle cx={p.x} cy={p.y} r={r + 7 * p.ping} fill="none" stroke="#00ffd5" strokeWidth={1.3} strokeOpacity={p.ping * 0.7} />
                )}
                <circle cx={p.x} cy={p.y} r={r} fill={p.ping > 0.3 ? "#ffffff" : baseCol} fillOpacity={0.42 + p.z * 0.55} />
              </g>
            );
          })}

          {/* Radar sweep beam rotating across Earth */}
          <g transform={`rotate(${sweepDeg} ${cx} ${cy})`}>
            <path
              d={`M ${cx} ${cy} L ${cx + R * 1.1} ${cy} A ${R * 1.1} ${R * 1.1} 0 0 0 ${cx + R * 0.78} ${cy - R * 0.78} Z`}
              fill="#00ffd5"
              fillOpacity={0.18}
            />
            <line x1={cx} y1={cy} x2={cx + R * 1.05} y2={cy} stroke="#00ffd5" strokeWidth={2.2} strokeOpacity={0.85} />
          </g>
        </g>

        {/* Crisp rim highlight on planet edge + subtle anamorphic horizon flare */}
        <circle cx={cx} cy={cy} r={R} fill="none" stroke="#00ffd5" strokeWidth={2.2} strokeOpacity={0.78} />
        <ellipse cx={cx} cy={cy - R * 0.92} rx={R * 1.45} ry={3.5} fill="url(#anamorphicFlare)" opacity={0.7} />
      </svg>

      {/* Coins passing in front of the planet */}
      {frontCoins.map(renderCoin)}
    </AbsoluteFill>
  );
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

      {/* 3D orbital radar rings tilted in deep background (or full Cosmic Earth-Radar + orbiting coins) */}
      {IS_COSMIC ? (
        <CosmicEarthRadarLayer />
      ) : (
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
      )}

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
        borderTop: `1.5px solid ${accent}88`,
        boxShadow: IS_LIGHT
          ? "0 10px 26px rgba(15,23,42,0.12)"
          : `0 16px 38px rgba(0,0,0,0.52), inset 0 1px 0 rgba(255,255,255,0.10)`,
      }}
    >
      <div style={{ width: 11, height: 11, marginTop: 9, borderRadius: "50%", backgroundColor: accent, boxShadow: `0 0 14px ${accent}`, flexShrink: 0 }} />
      <div>
        <div
          style={{
            fontSize: IS_PORTRAIT ? 25 : 26,
            fontWeight: 800,
            color: TEXT,
            textShadow: IS_LIGHT ? "none" : "0 2px 8px rgba(0,0,0,0.75)",
          }}
        >
          {title}
        </div>
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

const Hero3DSlide: React.FC<{ slide: ResolvedSlide }> = ({ slide }) => {
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

const CodeSplitSlide: React.FC<{ slide: ResolvedSlide }> = ({ slide }) => (
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
const QuoteSlide: React.FC<{ slide: ResolvedSlide }> = ({ slide }) => {
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
          maxWidth: IS_PORTRAIT ? "100%" : 1040,
          background: THEME.cardBg,
          border: `1.5px solid ${CYAN}55`,
          borderTop: `2px solid ${CYAN}`,
          borderRadius: 22,
          padding: IS_PORTRAIT ? "22px 24px" : "26px 32px",
          boxShadow: "0 20px 48px rgba(0,0,0,0.6)",
          fontSize: IS_PORTRAIT ? 46 : 52,
          fontWeight: 800,
          lineHeight: 1.22,
          color: TEXT,
        }}
      >
        {slide.title}
      </div>
      <div style={{ height: 4, width: `${rule}%`, maxWidth: 360, background: `linear-gradient(90deg, ${CYAN}, ${VIOLET})`, borderRadius: 2 }} />
      {slide.subtitle && <div style={{ fontSize: 26, color: MUTED }}>{slide.subtitle}</div>}
    </div>
  );
};

const KpiSlide: React.FC<{ slide: ResolvedSlide }> = ({ slide }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const kpis = slide.kpis ?? [];
  const cols = IS_PORTRAIT ? 1 : Math.min(Math.max(kpis.length, 1), 2);
  return (
    <div style={{ width: "100%", display: "flex", flexDirection: "column", gap: IS_PORTRAIT ? 28 : 22 }}>
      <EmbossedTitle fontSize={IS_PORTRAIT ? 52 : 58} lineHeight={1.08}>{slide.title}</EmbossedTitle>
      {slide.subtitle && <div style={{ fontSize: 24, color: MUTED }}>{slide.subtitle}</div>}
      <div style={{ display: "grid", gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: 24, marginTop: 8 }}>
        {kpis.map((k, i) => {
          const s = spring({ frame: frame - (10 + i * 10), fps, config: { damping: 180 } });
          const accent = [CYAN, BLUE, VIOLET, PINK][i % 4];
          const numLiftShadow = IS_LIGHT
            ? `0 2px 0 rgba(15,23,42,0.18), 0 8px 18px rgba(15,23,42,0.16)`
            : `0 1px 0 #0b2444, 0 2px 0 #091d38, 0 3px 0 #07162e, 0 4px 0 #050f22, 0 6px 0 #020814, 0 14px 28px rgba(0,0,0,0.88), 0 0 26px ${accent}cc, 0 0 48px ${accent}55`;
          return (
            <div
              key={`${k.value}-${i}`}
              style={{
                opacity: s,
                transform: `scale(${0.9 + 0.1 * s}) translateY(${(1 - s) * 18}px)`,
                background: THEME.cardBg,
                border: `1.5px solid ${accent}55`,
                borderTop: `2px solid ${accent}`,
                borderRadius: 22,
                padding: IS_PORTRAIT ? "20px 22px" : "24px 28px",
                boxShadow: IS_LIGHT
                  ? `0 12px 28px rgba(15,23,42,0.10)`
                  : `0 20px 48px rgba(0,0,0,0.62), 0 0 30px ${accent}28, inset 0 1px 0 rgba(255,255,255,0.12)`,
                display: "flex",
                flexDirection: "column",
                justifyContent: "space-between",
                gap: 12,
              }}
            >
              <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16 }}>
                <div
                  style={{
                    fontSize: IS_PORTRAIT ? 68 : 86,
                    fontWeight: 900,
                    lineHeight: 0.98,
                    letterSpacing: "-0.02em",
                    color: IS_LIGHT ? accent : "#ffffff",
                    textShadow: numLiftShadow,
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

const ScreenSplitSlide: React.FC<{ slide: ResolvedSlide; dur: number }> = ({ slide, dur }) => {
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

const UiRecordingSlide: React.FC<{ slide: ResolvedSlide }> = ({ slide }) => {
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

const Outro3DSlide: React.FC<{ slide: ResolvedSlide }> = ({ slide }) => {
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
const captionWrapStyle = (): React.CSSProperties => ({
  position: "absolute",
  left: IS_PORTRAIT ? 40 : 120,
  right: IS_PORTRAIT ? 40 : 120,
  bottom: IS_PORTRAIT ? 48 : 26,
  display: "flex",
  justifyContent: "center",
  pointerEvents: "none",
});

const CaptionKaraokeLayer: React.FC<{ cue: CaptionCue; sec: number }> = ({ cue, sec }) => {
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
          <span style={{ color: cue.speaker === "B" ? PINK : CYAN, marginRight: 10, fontFamily: "Consolas, monospace" }}>
            [{cue.speaker}]
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

const CaptionBoldLayer: React.FC<{ cue: CaptionCue }> = ({ cue }) => (
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
      {cue.speaker && (
        <span style={{ color: cue.speaker === "B" ? PINK : CYAN, marginRight: 14 }}>[{cue.speaker}]</span>
      )}
      {cue.text}
    </div>
  </div>
);

const CaptionOverlay: React.FC<{ captions?: CaptionCue[]; style?: "box" | "karaoke" | "bold" }> = ({
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

const CaptionOverlayBox: React.FC<{ captions?: CaptionCue[] }> = ({ captions }) => {
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
        {active.speaker && (
          <span style={{ color: active.speaker === "B" ? PINK : CYAN, marginRight: 10, fontFamily: "Consolas, monospace" }}>
            [{active.speaker}]
          </span>
        )}
        {active.text}
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
    if (slide.type === "ui_recording") return <UiRecordingSlide slide={slide} />;
    if (slide.type === "arch_flow") return <ArchFlowSlide slide={slide} />;
    if (slide.type === "outro_3d") return <Outro3DSlide slide={slide} />;
    if (slide.type === "timeline") return <TimelineSlide slide={slide} />;
    if (slide.type === "terminal") return <TerminalSlide slide={slide} />;
    if (slide.type === "kpi") return <KpiSlide slide={slide} />;
    if (slide.type === "quote") return <QuoteSlide slide={slide} />;
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
        {showCaptions && <CaptionOverlay captions={slide.captions} style={DECK.caption_style ?? "box"} />}
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
