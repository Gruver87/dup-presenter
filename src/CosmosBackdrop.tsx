import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";

interface WarpProps {
  width: number;
  height: number;
}

interface LightBeam {
  id: number;
  angleDeg: number;
  speed: number;
  phase: number;
  color: string;
  width: number;
  tailLen: number;
  isBlocked?: boolean; // red fail-closed packets stop at the outer shield radius
}

const BEAMS: LightBeam[] = [
  // Left flank — incoming cyan & gold transaction streams pulling toward center
  { id: 0, angleDeg: 156, speed: 0.011, phase: 0.05, color: "#00f0ff", width: 3.4, tailLen: 0.22 },
  { id: 1, angleDeg: 168, speed: 0.014, phase: 0.38, color: "#10ff88", width: 2.8, tailLen: 0.19 },
  { id: 2, angleDeg: 179, speed: 0.009, phase: 0.72, color: "#ffb800", width: 3.2, tailLen: 0.24 },
  { id: 3, angleDeg: 191, speed: 0.013, phase: 0.18, color: "#00f0ff", width: 2.6, tailLen: 0.2 },
  { id: 4, angleDeg: 204, speed: 0.010, phase: 0.56, color: "#a855f7", width: 3.0, tailLen: 0.21 },
  { id: 5, angleDeg: 144, speed: 0.012, phase: 0.84, color: "#ff2e63", width: 3.2, tailLen: 0.16, isBlocked: true },
  { id: 6, angleDeg: 216, speed: 0.011, phase: 0.42, color: "#ff2e63", width: 2.8, tailLen: 0.15, isBlocked: true },

  // Right flank — verified emerald, cyan & gold streams radiating/orbiting in depth
  { id: 7, angleDeg: -24, speed: 0.012, phase: 0.14, color: "#10ff88", width: 3.4, tailLen: 0.23 },
  { id: 8, angleDeg: -11, speed: 0.010, phase: 0.49, color: "#00f0ff", width: 3.0, tailLen: 0.21 },
  { id: 9, angleDeg: 2, speed: 0.014, phase: 0.81, color: "#ffb800", width: 3.2, tailLen: 0.22 },
  { id: 10, angleDeg: 14, speed: 0.009, phase: 0.27, color: "#10ff88", width: 2.8, tailLen: 0.2 },
  { id: 11, angleDeg: 27, speed: 0.013, phase: 0.63, color: "#a855f7", width: 3.0, tailLen: 0.19 },
  { id: 12, angleDeg: -36, speed: 0.011, phase: 0.91, color: "#ff2e63", width: 2.8, tailLen: 0.15, isBlocked: true },
  { id: 13, angleDeg: 38, speed: 0.012, phase: 0.33, color: "#00f0ff", width: 2.4, tailLen: 0.18 },

  // Top & bottom deep-tunnel streams
  { id: 14, angleDeg: -118, speed: 0.0085, phase: 0.2, color: "#00f0ff", width: 2.4, tailLen: 0.2 },
  { id: 15, angleDeg: -95, speed: 0.0105, phase: 0.65, color: "#ffb800", width: 2.6, tailLen: 0.18 },
  { id: 16, angleDeg: -66, speed: 0.0095, phase: 0.44, color: "#10ff88", width: 2.5, tailLen: 0.2 },
  { id: 17, angleDeg: 64, speed: 0.010, phase: 0.11, color: "#a855f7", width: 2.6, tailLen: 0.2 },
  { id: 18, angleDeg: 92, speed: 0.0088, phase: 0.52, color: "#10ff88", width: 2.8, tailLen: 0.22 },
  { id: 19, angleDeg: 118, speed: 0.0115, phase: 0.78, color: "#00f0ff", width: 2.6, tailLen: 0.19 },
  { id: 20, angleDeg: 132, speed: 0.009, phase: 0.29, color: "#ffb800", width: 2.3, tailLen: 0.17 },
  { id: 21, angleDeg: -48, speed: 0.010, phase: 0.06, color: "#10ff88", width: 2.5, tailLen: 0.18 },
];

const STARS = Array.from({ length: 56 }, (_, i) => ({
  angle: ((i * 137.508) % 360) * (Math.PI / 180),
  baseR: 0.14 + ((i * 29) % 86) / 100,
  size: 1.3 + (i % 3) * 0.85,
  speed: 0.0012 + (i % 5) * 0.00045,
  color: ["#e0f2fe", "#00f0ff", "#10ff88", "#ffb800", "#ff2e63", "#c084fc"][i % 6],
}));

/**
 * Deep concave 3D cosmic warp tunnel: draws the eye and side columns inward
 * toward a glowing central gravity well, while multi-colored transaction light
 * beams stream along the flanks and depth rails.
 */
export const QuantumWarpBackdrop: React.FC<WarpProps> = ({ width, height }) => {
  const frame = useCurrentFrame();
  const cx = width / 2;
  const cy = height * 0.51;
  const maxR = Math.hypot(cx, cy) * 1.08;
  const breathe = Math.sin(frame / 48) * 18;
  const twistRad = Math.sin(frame / 90) * 0.045;

  // 9 concentric elliptical depth rings pulled steadily inward to the center
  const ringCount = 9;
  const rings = Array.from({ length: ringCount }, (_, i) => {
    const raw = (1 - ((i / ringCount + frame * 0.0032) % 1));
    const eased = Math.pow(raw, 2.05);
    const rx = 95 + eased * (width * 0.64);
    const ry = 54 + eased * (height * 0.62);
    const opacity = Math.sin(raw * Math.PI) * 0.34;
    const stroke = i % 3 === 0 ? "#00f0ff" : i % 3 === 1 ? "#10ff88" : "#a855f7";
    return { rx, ry, opacity, stroke, sw: 0.9 + eased * 1.8 };
  });

  // 24 radial warp meridians converging into the central gravity well
  const spokes = Array.from({ length: 24 }, (_, i) => {
    const a = (i / 24) * Math.PI * 2 + twistRad;
    const x1 = cx + Math.cos(a) * 62;
    const y1 = cy + Math.sin(a) * 36;
    const x2 = cx + Math.cos(a) * maxR;
    const y2 = cy + Math.sin(a) * maxR;
    const isMajor = i % 3 === 0;
    const color = i % 6 === 0 ? "#00f0ff" : i % 6 === 2 ? "#10ff88" : i % 6 === 4 ? "#ff2e63" : "#6366f1";
    return { x1, y1, x2, y2, isMajor, color };
  });

  return (
    <AbsoluteFill style={{ backgroundColor: "#020512", overflow: "hidden" }}>
      {/* Deep multi-tone cosmic nebulae around the flanks (rich semantic hues, dark center contrast) */}
      <div
        style={{
          position: "absolute",
          width: 980,
          height: 980,
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(0,240,255,0.22) 0%, rgba(14,165,233,0.08) 45%, transparent 72%)",
          left: -260 + Math.sin(frame / 72) * 55,
          top: -120 + Math.cos(frame / 85) * 45,
          filter: "blur(36px)",
        }}
      />
      <div
        style={{
          position: "absolute",
          width: 960,
          height: 960,
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(16,255,136,0.20) 0%, rgba(16,185,129,0.06) 46%, transparent 72%)",
          right: -240 + Math.cos(frame / 76) * 55,
          bottom: -180 + Math.sin(frame / 66) * 45,
          filter: "blur(38px)",
        }}
      />
      <div
        style={{
          position: "absolute",
          width: 820,
          height: 820,
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(255,46,99,0.19) 0%, rgba(168,85,247,0.07) 48%, transparent 74%)",
          left: -180 + Math.cos(frame / 68) * 40,
          bottom: -240 + Math.sin(frame / 74) * 35,
          filter: "blur(38px)",
        }}
      />
      <div
        style={{
          position: "absolute",
          width: 780,
          height: 780,
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(255,184,0,0.16) 0%, rgba(168,85,247,0.07) 46%, transparent 72%)",
          right: -140 + Math.sin(frame / 64) * 45,
          top: -210 + Math.cos(frame / 70) * 40,
          filter: "blur(36px)",
        }}
      />

      {/* Central gravity-well glow (pulls visual focus into the deep center) */}
      <div
        style={{
          position: "absolute",
          left: cx - 340,
          top: cy - 220,
          width: 680,
          height: 440,
          borderRadius: "50%",
          background:
            "radial-gradient(ellipse at center, rgba(0,240,255,0.15) 0%, rgba(168,85,247,0.10) 38%, rgba(2,5,18,0.0) 74%)",
          transform: `scale(${1 + Math.sin(frame / 36) * 0.06})`,
          filter: "blur(24px)",
        }}
      />

      {/* Concave 3D Warp Tunnel + Side Dome Arcs + Transaction Light Beams */}
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        style={{ position: "absolute", inset: 0, pointerEvents: "none" }}
      >
        <defs>
          <filter id="beamBloom" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="5.5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <radialGradient id="coreWell" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#00f0ff" stopOpacity="0.28" />
            <stop offset="35%" stopColor="#a855f7" stopOpacity="0.10" />
            <stop offset="100%" stopColor="#020512" stopOpacity="0" />
          </radialGradient>
        </defs>

        {/* Converging tunnel meridians */}
        {spokes.map((sp, i) => (
          <line
            key={`sp-${i}`}
            x1={sp.x1}
            y1={sp.y1}
            x2={sp.x2}
            y2={sp.y2}
            stroke={sp.color}
            strokeWidth={sp.isMajor ? 1.4 : 0.75}
            opacity={sp.isMajor ? 0.22 : 0.1}
          />
        ))}

        {/* Inflated concave dome arcs on left & right edges (curved lens depth feel) */}
        {[0, 1, 2].map((k) => {
          const offset = k * 78 + breathe * 0.45;
          const op = 0.22 - k * 0.055;
          return (
            <g key={`arc-${k}`} fill="none">
              <path
                d={`M ${-40 + offset} -60 Q ${220 + offset} ${cy} ${-40 + offset} ${height + 60}`}
                stroke={k === 0 ? "#00f0ff" : k === 1 ? "#ff2e63" : "#a855f7"}
                strokeWidth={1.6 - k * 0.3}
                opacity={op}
              />
              <path
                d={`M ${width + 40 - offset} -60 Q ${width - 220 - offset} ${cy} ${width + 40 - offset} ${height + 60}`}
                stroke={k === 0 ? "#10ff88" : k === 1 ? "#ffb800" : "#00f0ff"}
                strokeWidth={1.6 - k * 0.3}
                opacity={op}
              />
            </g>
          );
        })}

        {/* Concentric depth rings pulled into center */}
        {rings.map((r, i) => (
          <ellipse
            key={`ring-${i}`}
            cx={cx}
            cy={cy}
            rx={r.rx}
            ry={r.ry}
            fill="none"
            stroke={r.stroke}
            strokeWidth={r.sw}
            opacity={r.opacity}
            strokeDasharray={i % 2 === 0 ? "none" : "10 12"}
          />
        ))}

        {/* Deep central portal halo */}
        <ellipse cx={cx} cy={cy} rx={170 + breathe * 0.5} ry={102 + breathe * 0.3} fill="url(#coreWell)" />

        {/* Parallax starfield drifting inward */}
        {STARS.map((st, i) => {
          const rNorm = 1 - ((st.baseR + frame * st.speed) % 0.92);
          const r = Math.pow(rNorm, 1.7) * maxR;
          const x = cx + Math.cos(st.angle + twistRad * 1.4) * r;
          const y = cy + Math.sin(st.angle + twistRad * 1.4) * r * 0.72;
          const op = Math.min(0.85, Math.sin(rNorm * Math.PI) * 0.95);
          return <circle key={`st-${i}`} cx={x} cy={y} r={st.size * (0.5 + rNorm * 0.8)} fill={st.color} opacity={op} />;
        })}

        {/* Transaction Light Beams streaming from flanks & depth into the core */}
        {BEAMS.map((b) => {
          const a = (b.angleDeg * Math.PI) / 180 + twistRad * 0.8;
          const rawT = (frame * b.speed + b.phase) % 1;
          // Blocked red fail-closed beams stop at outer shield radius (0.56) and flash-deflect
          const minR = b.isBlocked ? 0.54 : 0.08;
          const headNorm = 1.04 - rawT * (1.04 - minR);
          const tailNorm = Math.min(1.08, headNorm + b.tailLen * (0.45 + headNorm * 0.7));

          const rHead = Math.pow(Math.max(0.02, headNorm), 1.55) * maxR;
          const rTail = Math.pow(Math.max(0.02, tailNorm), 1.55) * maxR;
          const hx = cx + Math.cos(a) * rHead;
          const hy = cy + Math.sin(a) * rHead * 0.78;
          const tx = cx + Math.cos(a) * rTail;
          const ty = cy + Math.sin(a) * rTail * 0.78;
          const gradId = `beamGrad-${b.id}`;
          const beamOp = b.isBlocked
            ? rawT > 0.82
              ? Math.max(0, (1 - rawT) * 5.2)
              : Math.min(0.95, rawT * 3.5)
            : Math.sin(rawT * Math.PI) * 0.96;

          return (
            <g key={gradId} opacity={beamOp}>
              <defs>
                <linearGradient id={gradId} gradientUnits="userSpaceOnUse" x1={tx} y1={ty} x2={hx} y2={hy}>
                  <stop offset="0%" stopColor={b.color} stopOpacity="0" />
                  <stop offset="65%" stopColor={b.color} stopOpacity="0.65" />
                  <stop offset="100%" stopColor="#ffffff" stopOpacity="1" />
                </linearGradient>
              </defs>
              <line
                x1={tx}
                y1={ty}
                x2={hx}
                y2={hy}
                stroke={`url(#${gradId})`}
                strokeWidth={b.width * (0.65 + headNorm * 0.7)}
                strokeLinecap="round"
                filter="url(#beamBloom)"
              />
              <circle cx={hx} cy={hy} r={b.width * 1.15} fill="#ffffff" filter="url(#beamBloom)" />
              <circle cx={hx} cy={hy} r={b.width * 2.1} fill={b.color} opacity={0.42} />
              {/* Red fail-closed shield spark when a blocked packet hits the perimeter */}
              {b.isBlocked && rawT > 0.74 && (
                <circle
                  cx={hx}
                  cy={hy}
                  r={10 + (rawT - 0.74) * 95}
                  fill="none"
                  stroke="#ff2e63"
                  strokeWidth={2.2}
                  opacity={Math.max(0, (1 - rawT) * 3.8)}
                />
              )}
            </g>
          );
        })}
      </svg>

      {/* Subtle radial depth vignette to emphasize the inflated concave lens feeling */}
      <AbsoluteFill
        style={{
          background:
            "radial-gradient(ellipse at 50% 50%, rgba(2,5,18,0) 52%, rgba(1,3,12,0.52) 86%, rgba(1,2,10,0.78) 100%)",
          pointerEvents: "none",
        }}
      />
    </AbsoluteFill>
  );
};
