import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
} from "remotion";
import { BLUE, CYAN, HEIGHT, IS_PORTRAIT, VIOLET, WIDTH } from "./deckContext";

export const COSMIC_STARS = Array.from({ length: 92 }, (_, i) => ({
  x: ((i * 223 + 47) % Math.max(200, WIDTH)),
  y: ((i * 157 + 31) % Math.max(200, HEIGHT)),
  r: (i % 4 === 0 ? 2.4 : i % 3 === 0 ? 1.7 : 1.1),
  phase: i * 0.7,
  speed: 0.05 + (i % 5) * 0.025,
  color: i % 9 === 0 ? "#fde68a" : i % 5 === 0 ? "#bae6fd" : "#ffffff",
}));

// Selected top-100 coins orbiting the radar planet (balanced count, no clutter)

export const ORBIT_COINS = [
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

export const EARTH_LAND_POINTS: { lat: number; lon: number; hot?: boolean }[] = (() => {
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

export const CryptoMiniChart: React.FC<{
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

export const EXCHANGE_NODES: { name: string; x: number; y: number; color: string }[] = [
  { name: "Binance", x: 0.4, y: 0.08, color: "#facc15" },
  { name: "Bybit", x: 0.66, y: 0.08, color: "#fb923c" },
  { name: "KuCoin", x: 0.4, y: 0.83, color: "#00ffd5" },
  { name: "MEXC", x: 0.66, y: 0.83, color: "#38bdf8" },
];

export const ExchangeFlowLayer: React.FC<{ cx: number; cy: number }> = ({ cx, cy }) => {
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

export const CosmicEarthRadarLayer: React.FC = () => {
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
