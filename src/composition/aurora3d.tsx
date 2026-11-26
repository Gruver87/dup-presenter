import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
} from "remotion";
import { CosmicEarthRadarLayer } from "./cosmicBackdrop";
import { BG, BLUE, CYAN, DECK, HEIGHT, IS_COSMIC, IS_PORTRAIT, PINK, TEXT, THEME, VIOLET, WIDTH } from "./deckContext";

export const PARTICLES = Array.from({ length: 28 }, (_, i) => ({
  x: ((i * 197 + 83) % Math.max(200, WIDTH - 80)) + 40,
  y: ((i * 131 + 59) % Math.max(200, HEIGHT - 100)) + 50,
  r: (i % 3) * 2.2 + 2.5,
  speed: 0.35 + (i % 5) * 0.22,
  color: [CYAN, BLUE, VIOLET, PINK][i % 4],
}));

export const HEX_SHARDS = Array.from({ length: 8 }, (_, i) => ({
  x: ((i * 271 + 140) % Math.max(300, WIDTH - 200)) + 100,
  y: ((i * 173 + 110) % Math.max(300, HEIGHT - 200)) + 100,
  size: 44 + (i % 4) * 18,
  speed: 0.5 + (i % 3) * 0.3,
  color: [CYAN, BLUE, VIOLET, PINK][i % 4],
}));

export const Aurora3DBackdrop: React.FC = () => {
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

export const Cube3D: React.FC<{ size?: number; faces?: string[] }> = ({
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
    // Hide the far side of each face: otherwise the back walls show through the transparent front
    // face as mirrored text (seen as reversed labels on the cube). Near faces stay visible.
    backfaceVisibility: "hidden",
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
