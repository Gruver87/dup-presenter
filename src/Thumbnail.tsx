import React from "react";
import { AbsoluteFill, Composition, Img, staticFile } from "remotion";
import { THEMES, type ThemeId } from "./themes";

export interface ThumbnailProps {
  title: string;
  subtitle?: string;
  kicker?: string;
  accentBadge?: string;
  brand?: string;
  theme?: ThemeId;
  previewImage?: string;
}

export const ThumbnailCanvas: React.FC<ThumbnailProps> = ({
  title,
  subtitle = "",
  kicker = "DUP PRESENTER · 3D STUDIO",
  accentBadge = "1080P · -16 LUFS",
  brand = "DUP LABS",
  theme = "quantum_ledger",
  previewImage = "",
}) => {
  const pal = THEMES[theme] ?? THEMES.quantum_ledger;
  const hasPreview = Boolean(previewImage && previewImage.trim());

  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(ellipse at 50% 50%, ${pal.accent1}22 0%, #050c24 55%, #020512 100%)`,
        fontFamily: "Segoe UI, Inter, Arial, sans-serif",
        overflow: "hidden",
        padding: "54px 64px",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
      }}
    >
      {/* Concentric cosmic warp rings */}
      <svg
        width={1280}
        height={720}
        viewBox="0 0 1280 720"
        style={{ position: "absolute", inset: 0, pointerEvents: "none", opacity: 0.55 }}
      >
        {[160, 290, 440, 610].map((r, i) => (
          <ellipse
            key={r}
            cx={640}
            cy={360}
            rx={r * 1.45}
            ry={r * 0.84}
            fill="none"
            stroke={i % 2 === 0 ? pal.accent1 : pal.accent4}
            strokeWidth={1.6}
            strokeDasharray={i % 2 === 1 ? "10 10" : undefined}
            opacity={0.45 - i * 0.08}
          />
        ))}
        {/* Transaction light streaks */}
        <line x1={40} y1={110} x2={460} y2={280} stroke={pal.accent1} strokeWidth={3} opacity={0.7} />
        <line x1={1240} y1={130} x2={820} y2={290} stroke={pal.accent2} strokeWidth={3} opacity={0.7} />
        <line x1={80} y1={640} x2={480} y2={460} stroke={pal.accent4} strokeWidth={3} opacity={0.7} />
        <line x1={1210} y1={620} x2={840} y2={470} stroke={pal.accent3} strokeWidth={3} opacity={0.7} />
      </svg>

      {/* Top bar */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", zIndex: 2 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <div
            style={{
              width: 18,
              height: 18,
              borderRadius: 6,
              background: pal.accent2,
              boxShadow: `0 0 18px ${pal.accent2}`,
            }}
          />
          <span style={{ fontSize: 22, fontWeight: 900, letterSpacing: 2.2, color: "#ffffff" }}>{brand}</span>
          <span
            style={{
              padding: "6px 16px",
              borderRadius: 999,
              border: `1.5px solid ${pal.accent1}`,
              background: "rgba(3,12,34,0.85)",
              color: pal.accent1,
              fontFamily: "Consolas, monospace",
              fontSize: 15,
              fontWeight: 900,
              letterSpacing: 1.4,
            }}
          >
            {kicker}
          </span>
        </div>

        <div
          style={{
            padding: "8px 18px",
            borderRadius: 999,
            border: `2px solid ${pal.accent2}`,
            background: `${pal.accent2}24`,
            color: "#ffffff",
            fontFamily: "Consolas, monospace",
            fontSize: 16,
            fontWeight: 900,
            boxShadow: `0 0 24px ${pal.accent2}66`,
          }}
        >
          {accentBadge}
        </div>
      </div>

      {/* Main focal row */}
      <div style={{ display: "flex", alignItems: "center", gap: 40, zIndex: 2, flex: 1, marginTop: 18 }}>
        <div style={{ flex: hasPreview ? 1.1 : 1, display: "flex", flexDirection: "column", gap: 18 }}>
          <div
            style={{
              fontSize: hasPreview ? 72 : 88,
              fontWeight: 900,
              lineHeight: 0.98,
              letterSpacing: -2,
              color: "#ffffff",
              textShadow: `0 3px 0 #071329, 0 6px 0 #020612, 0 18px 34px rgba(0,0,0,0.95), 0 0 36px ${pal.accent1}cc`,
            }}
          >
            {title}
          </div>
          {subtitle && (
            <div style={{ fontSize: 28, fontWeight: 700, color: "#cbd5e1", lineHeight: 1.28, maxWidth: 820 }}>
              {subtitle}
            </div>
          )}
        </div>

        {hasPreview && (
          <div
            style={{
              width: 480,
              height: 320,
              borderRadius: 22,
              overflow: "hidden",
              border: `2.5px solid ${pal.accent1}`,
              boxShadow: `0 22px 48px rgba(0,0,0,0.85), 0 0 36px ${pal.accent1}66`,
              transform: "perspective(1100px) rotateY(-8deg)",
              flexShrink: 0,
            }}
          >
            <Img src={staticFile(previewImage)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
          </div>
        )}
      </div>

      {/* Bottom neon bar */}
      <div
        style={{
          height: 7,
          borderRadius: 999,
          background: `linear-gradient(90deg, ${pal.accent1}, ${pal.accent2}, ${pal.accent3}, ${pal.accent4})`,
          boxShadow: `0 0 22px ${pal.accent1}aa`,
          zIndex: 2,
        }}
      />
    </AbsoluteFill>
  );
};

export const DupThumbnailComposition: React.FC = () => (
  <Composition
    id="DupThumbnail"
    component={ThumbnailCanvas as unknown as React.FC<Record<string, unknown>>}
    durationInFrames={1}
    fps={30}
    width={1280}
    height={720}
    defaultProps={{
      title: "DUP Protocol Inside",
      subtitle: "Living 3D architecture: Python orchestrates, Rust drives the core",
      kicker: "DUP LABS · LAYER 1",
      accentBadge: "0 FLOAT · 48H PASS",
      brand: "DUP LABS",
      theme: "quantum_ledger",
      previewImage: "",
    }}
  />
);
