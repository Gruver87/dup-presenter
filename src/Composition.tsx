import {
  AbsoluteFill,
  Audio,
  Img,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { CalculateMetadataFunction, Composition } from "remotion";
import rawDeck from "./generated/deck_resolved.json";
import type { ResolvedDeck, ResolvedSlide } from "./types";

const DECK = rawDeck as unknown as ResolvedDeck;
const FPS = DECK.fps || 30;
const DURATION = DECK.total_seconds * FPS;

type Props = Record<string, unknown>;

const calculateMetadata: CalculateMetadataFunction<Props> = () => {
  return {
    durationInFrames: DURATION,
    fps: FPS,
    width: DECK.width || 1920,
    height: DECK.height || 1080,
  };
};

const BG = "#050714";
const CYAN = "#00f5d4";
const BLUE = "#38bdf8";
const VIOLET = "#c084fc";
const PINK = "#f472b6";
const TEXT = "#f8fafc";
const MUTED = "#cbd5e1";

const GRADIENT_TITLE: React.CSSProperties = {
  background: `linear-gradient(95deg, ${CYAN} 0%, ${BLUE} 48%, ${VIOLET} 100%)`,
  WebkitBackgroundClip: "text",
  WebkitTextFillColor: "transparent",
};

const PARTICLES = Array.from({ length: 22 }, (_, i) => ({
  x: ((i * 197 + 83) % 1840) + 40,
  y: ((i * 131 + 59) % 980) + 50,
  r: (i % 3) * 2.5 + 3,
  speed: 0.4 + (i % 5) * 0.25,
  color: [CYAN, BLUE, VIOLET, PINK][i % 4],
}));

const Aurora3DBackdrop: React.FC = () => {
  const frame = useCurrentFrame();
  const gridShift = (frame * 2.4) % 80;

  return (
    <AbsoluteFill style={{ backgroundColor: BG, overflow: "hidden" }}>
      <div
        style={{
          position: "absolute",
          width: 980,
          height: 980,
          borderRadius: "50%",
          background:
            "radial-gradient(circle, rgba(0,245,212,0.22) 0%, rgba(56,189,248,0.08) 45%, rgba(5,7,20,0) 72%)",
          left: -120 + Math.sin(frame / 75) * 90,
          top: -220 + Math.cos(frame / 90) * 60,
          filter: "blur(30px)",
        }}
      />
      <div
        style={{
          position: "absolute",
          width: 1050,
          height: 1050,
          borderRadius: "50%",
          background:
            "radial-gradient(circle, rgba(192,132,252,0.22) 0%, rgba(244,114,182,0.10) 45%, rgba(5,7,20,0) 72%)",
          right: -180 + Math.cos(frame / 80) * 90,
          bottom: -260 + Math.sin(frame / 70) * 60,
          filter: "blur(32px)",
        }}
      />
      <div
        style={{
          position: "absolute",
          width: 760,
          height: 760,
          borderRadius: "50%",
          background:
            "radial-gradient(circle, rgba(56,189,248,0.18) 0%, rgba(5,7,20,0) 70%)",
          left: 580 + Math.sin(frame / 60) * 110,
          top: 180 + Math.cos(frame / 65) * 80,
          filter: "blur(28px)",
        }}
      />
      <div
        style={{
          position: "absolute",
          left: -400,
          right: -400,
          bottom: -140,
          height: 620,
          perspective: 700,
          overflow: "hidden",
          opacity: 0.45,
        }}
      >
        <div
          style={{
            width: "100%",
            height: "180%",
            transform: "rotateX(70deg)",
            transformOrigin: "center bottom",
            backgroundImage:
              "linear-gradient(rgba(56,189,248,0.28) 1px, transparent 1px), linear-gradient(90deg, rgba(192,132,252,0.24) 1px, transparent 1px)",
            backgroundSize: "80px 80px",
            backgroundPosition: `0px ${gridShift}px`,
          }}
        />
      </div>
      {PARTICLES.map((p, idx) => {
        const py = ((p.y - frame * p.speed + 1200) % 1120) - 20;
        const px = p.x + Math.sin((frame + idx * 20) / 45) * 18;
        return (
          <div
            key={idx}
            style={{
              position: "absolute",
              left: px,
              top: py,
              width: p.r * 2,
              height: p.r * 2,
              borderRadius: "50%",
              backgroundColor: p.color,
              opacity: 0.55,
              boxShadow: `0 0 14px ${p.color}`,
            }}
          />
        );
      })}
    </AbsoluteFill>
  );
};

const Cube3D: React.FC<{ size?: number; faces?: string[] }> = ({
  size = 210,
  faces = ["DUP", "L1", "RUST", "SPOT", "MESH", "EVM"],
}) => {
  const frame = useCurrentFrame();
  const half = size / 2;
  const rx = 22 + Math.sin(frame / 40) * 14;
  const ry = frame * 1.4;
  const f = (i: number) => faces[i % faces.length] ?? "";

  const faceBase: React.CSSProperties = {
    position: "absolute",
    width: size,
    height: size,
    border: "2px solid rgba(0,245,212,0.75)",
    background:
      "linear-gradient(135deg, rgba(0,245,212,0.16), rgba(56,189,248,0.12), rgba(192,132,252,0.18))",
    boxShadow: "inset 0 0 28px rgba(56,189,248,0.25), 0 0 22px rgba(0,245,212,0.18)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 28,
    fontWeight: 800,
    color: TEXT,
    letterSpacing: 3,
    backfaceVisibility: "visible",
  };

  return (
    <div
      style={{
        width: size,
        height: size,
        perspective: 900,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div
        style={{
          width: size,
          height: size,
          position: "relative",
          transformStyle: "preserve-3d",
          transform: `rotateX(${rx}deg) rotateY(${ry}deg)`,
        }}
      >
        <div style={{ ...faceBase, transform: `translateZ(${half}px)` }}>{f(0)}</div>
        <div style={{ ...faceBase, transform: `rotateY(180deg) translateZ(${half}px)` }}>{f(1)}</div>
        <div style={{ ...faceBase, transform: `rotateY(90deg) translateZ(${half}px)` }}>{f(2)}</div>
        <div style={{ ...faceBase, transform: `rotateY(-90deg) translateZ(${half}px)` }}>{f(3)}</div>
        <div style={{ ...faceBase, transform: `rotateX(90deg) translateZ(${half}px)` }}>{f(4)}</div>
        <div style={{ ...faceBase, transform: `rotateX(-90deg) translateZ(${half}px)` }}>{f(5)}</div>
      </div>
    </div>
  );
};

const SlideChrome: React.FC<{
  brand: string;
  num: string;
  tag: string;
  dur: number;
  children: React.ReactNode;
}> = ({ brand, num, tag, dur, children }) => {
  const frame = useCurrentFrame();
  const fadeIn = interpolate(frame, [0, 14], [0, 1], { extrapolateRight: "clamp" });
  const fadeOut = interpolate(frame, [dur - 14, dur], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const slideX = interpolate(frame, [0, 14], [28, 0], { extrapolateRight: "clamp" });
  const opacity = Math.min(fadeIn, fadeOut);

  return (
    <AbsoluteFill
      style={{
        opacity,
        transform: `translateX(${slideX}px)`,
        fontFamily: "Segoe UI, Inter, Arial, sans-serif",
        padding: "42px 80px 54px 80px",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 26,
          borderBottom: "1px solid rgba(255,255,255,0.12)",
          paddingBottom: 16,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <div
            style={{
              width: 16,
              height: 16,
              borderRadius: 5,
              background: `linear-gradient(135deg, ${CYAN}, ${BLUE}, ${VIOLET})`,
              boxShadow: `0 0 16px ${CYAN}`,
            }}
          />
          <span style={{ fontSize: 22, fontWeight: 800, color: TEXT, letterSpacing: 3 }}>
            {brand}
          </span>
          <span
            style={{
              marginLeft: 10,
              padding: "5px 16px",
              borderRadius: 999,
              background:
                "linear-gradient(90deg, rgba(0,245,212,0.16), rgba(192,132,252,0.16))",
              border: "1px solid rgba(0,245,212,0.45)",
              color: CYAN,
              fontSize: 16,
              fontWeight: 700,
              letterSpacing: 2,
            }}
          >
            {tag}
          </span>
        </div>
        <div style={{ fontSize: 20, fontWeight: 700, color: BLUE, letterSpacing: 2 }}>
          {num}
        </div>
      </div>

      <div style={{ flex: 1, display: "flex", alignItems: "center" }}>{children}</div>
    </AbsoluteFill>
  );
};

const BulletItem: React.FC<{
  title: string;
  desc: string;
  delay: number;
  accent?: string;
}> = ({ title, desc, delay, accent = CYAN }) => {
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
        padding: "16px 20px",
        borderRadius: 16,
        background:
          "linear-gradient(135deg, rgba(255,255,255,0.06), rgba(255,255,255,0.02))",
        border: "1px solid rgba(255,255,255,0.12)",
        boxShadow: "0 10px 30px rgba(0,0,0,0.35)",
      }}
    >
      <div
        style={{
          width: 11,
          height: 11,
          marginTop: 10,
          borderRadius: "50%",
          backgroundColor: accent,
          boxShadow: `0 0 12px ${accent}`,
          flexShrink: 0,
        }}
      />
      <div>
        <div style={{ fontSize: 26, fontWeight: 700, color: TEXT }}>{title}</div>
        <div style={{ fontSize: 20, color: MUTED, marginTop: 4, lineHeight: 1.35 }}>
          {desc}
        </div>
      </div>
    </div>
  );
};

const CodeWindow3D: React.FC<{
  filename: string;
  lines: { text: string; color?: string }[];
  delay?: number;
}> = ({ filename, lines, delay = 12 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - delay, fps, config: { damping: 170 } });
  const rotY = interpolate(s, [0, 1], [-18, -6]) + Math.sin(frame / 45) * 2.2;
  const rotX = 3 + Math.cos(frame / 55) * 1.5;

  return (
    <div style={{ width: "100%", perspective: 1400 }}>
      <div
        style={{
          opacity: s,
          transform: `rotateY(${rotY}deg) rotateX(${rotX}deg)`,
          borderRadius: 20,
          overflow: "hidden",
          border: "1px solid rgba(56,189,248,0.5)",
          background: "rgba(11,15,28,0.92)",
          boxShadow:
            "0 30px 80px rgba(0,0,0,0.75), 0 0 40px rgba(56,189,248,0.16)",
        }}
      >
        <div
          style={{
            height: 42,
            background:
              "linear-gradient(90deg, rgba(56,189,248,0.14), rgba(192,132,252,0.14))",
            borderBottom: "1px solid rgba(255,255,255,0.10)",
            display: "flex",
            alignItems: "center",
            padding: "0 18px",
            gap: 8,
          }}
        >
          <div style={{ width: 11, height: 11, borderRadius: "50%", background: "#ff5f56" }} />
          <div style={{ width: 11, height: 11, borderRadius: "50%", background: "#ffbd2e" }} />
          <div style={{ width: 11, height: 11, borderRadius: "50%", background: "#27c93f" }} />
          <div
            style={{
              marginLeft: 12,
              fontSize: 17,
              color: TEXT,
              fontFamily: "Consolas, monospace",
            }}
          >
            {filename}
          </div>
        </div>
        <div
          style={{
            padding: "24px 28px",
            fontFamily: "Consolas, 'Cascadia Code', monospace",
            fontSize: 21,
            lineHeight: 1.55,
          }}
        >
          {lines.map((line, i) => {
            const lineOpacity = interpolate(
              frame,
              [delay + 6 + i * 3, delay + 14 + i * 3],
              [0, 1],
              { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
            );
            return (
              <div key={i} style={{ opacity: lineOpacity, display: "flex", gap: 18 }}>
                <span style={{ color: "#64748b", minWidth: 28, textAlign: "right" }}>
                  {i + 1}
                </span>
                <span style={{ color: line.color ?? "#e2e8f0", whiteSpace: "pre" }}>
                  {line.text}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

const ScreenWindow3D: React.FC<{
  src: string;
  caption: string;
  maxHeight?: number;
  delay?: number;
}> = ({ src, caption, maxHeight = 610, delay = 10 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - delay, fps, config: { damping: 170 } });
  const rotY = interpolate(s, [0, 1], [-16, -5]) + Math.sin(frame / 48) * 2.0;
  const rotX = 2.5 + Math.cos(frame / 58) * 1.4;
  const scale = interpolate(frame, [0, 360], [1.0, 1.045], { extrapolateRight: "clamp" });

  return (
    <div style={{ width: "100%", perspective: 1400 }}>
      <div
        style={{
          opacity: s,
          transform: `rotateY(${rotY}deg) rotateX(${rotX}deg)`,
          borderRadius: 20,
          overflow: "hidden",
          border: "1px solid rgba(0,245,212,0.5)",
          background: "#0b0f1c",
          boxShadow:
            "0 30px 80px rgba(0,0,0,0.75), 0 0 42px rgba(0,245,212,0.16)",
        }}
      >
        <div
          style={{
            height: 40,
            background:
              "linear-gradient(90deg, rgba(0,245,212,0.14), rgba(56,189,248,0.14))",
            borderBottom: "1px solid rgba(255,255,255,0.10)",
            display: "flex",
            alignItems: "center",
            padding: "0 16px",
            gap: 8,
          }}
        >
          <div style={{ width: 11, height: 11, borderRadius: "50%", background: "#ff5f56" }} />
          <div style={{ width: 11, height: 11, borderRadius: "50%", background: "#ffbd2e" }} />
          <div style={{ width: 11, height: 11, borderRadius: "50%", background: "#27c93f" }} />
          <div style={{ marginLeft: 12, fontSize: 16, color: TEXT }}>{caption}</div>
        </div>
        <div style={{ overflow: "hidden", maxHeight }}>
          <Img
            src={staticFile(src)}
            style={{
              width: "100%",
              height: "auto",
              display: "block",
              transform: `scale(${scale})`,
              transformOrigin: "center top",
            }}
          />
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
    <div style={{ width: "100%", display: "flex", alignItems: "center", gap: 70 }}>
      <div style={{ flex: 1.25, display: "flex", flexDirection: "column", gap: 26 }}>
        <div
          style={{
            fontSize: 122,
            fontWeight: 900,
            lineHeight: 1.02,
            opacity: s,
            ...GRADIENT_TITLE,
          }}
        >
          {slide.title}
        </div>
        {slide.subtitle && (
          <div style={{ fontSize: 36, color: TEXT, lineHeight: 1.32 }}>{slide.subtitle}</div>
        )}
        <div style={{ display: "flex", gap: 18, marginTop: 10, flexWrap: "wrap" }}>
          {(slide.pills ?? []).map((p, idx) => {
            const cs = spring({ frame: frame - (14 + idx * 7), fps, config: { damping: 180 } });
            return (
              <div
                key={p.name}
                style={{
                  opacity: cs,
                  padding: "14px 24px",
                  borderRadius: 14,
                  background: "rgba(255,255,255,0.05)",
                  border: `1px solid ${p.color}`,
                  color: p.color,
                  fontSize: 22,
                  fontWeight: 700,
                  boxShadow: `0 0 22px ${p.color}33`,
                }}
              >
                {p.name}
              </div>
            );
          })}
        </div>
      </div>
      <div style={{ flex: 0.75, display: "flex", justifyContent: "center" }}>
        <Cube3D size={230} faces={slide.cube_faces} />
      </div>
    </div>
  );
};

const CodeSplitSlide: React.FC<{ slide: ResolvedSlide }> = ({ slide }) => (
  <div style={{ width: "100%", display: "flex", gap: 54, alignItems: "center" }}>
    <div style={{ flex: 0.95, display: "flex", flexDirection: "column", gap: 18 }}>
      <div style={{ fontSize: 60, fontWeight: 900, lineHeight: 1.08, ...GRADIENT_TITLE }}>
        {slide.title}
      </div>
      {slide.subtitle && (
        <div style={{ fontSize: 26, color: MUTED, marginBottom: 6 }}>{slide.subtitle}</div>
      )}
      {(slide.bullets ?? []).map((b, idx) => (
        <BulletItem
          key={b.title}
          title={b.title}
          desc={b.desc}
          delay={10 + idx * 10}
          accent={b.accent}
        />
      ))}
    </div>
    <div style={{ flex: 1.15 }}>
      {slide.code && (
        <CodeWindow3D filename={slide.code.filename} lines={slide.code.lines} />
      )}
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
    <div style={{ width: "100%", display: "flex", gap: 48, alignItems: "center" }}>
      <div style={{ flex: 0.88, display: "flex", flexDirection: "column", gap: 18 }}>
        <div style={{ fontSize: 54, fontWeight: 900, lineHeight: 1.08, ...GRADIENT_TITLE }}>
          {slide.title}
        </div>
        {slide.subtitle && (
          <div style={{ fontSize: 24, color: MUTED, marginBottom: 4 }}>{slide.subtitle}</div>
        )}
        {(slide.bullets ?? []).map((b, idx) => (
          <BulletItem
            key={b.title}
            title={b.title}
            desc={b.desc}
            delay={10 + idx * 10}
            accent={b.accent}
          />
        ))}
      </div>
      <div style={{ flex: 1.32 }}>
        {active && (
          <ScreenWindow3D
            key={active.src}
            src={active.src}
            caption={active.caption}
            delay={activeIdx === 0 ? 8 : 0}
          />
        )}
      </div>
    </div>
  );
};

const Outro3DSlide: React.FC<{ slide: ResolvedSlide }> = ({ slide }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame, fps, config: { damping: 180 } });
  return (
    <div
      style={{
        width: "100%",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 60,
        opacity: s,
      }}
    >
      <div style={{ flex: 1.2, display: "flex", flexDirection: "column", gap: 24 }}>
        <div style={{ fontSize: 96, fontWeight: 900, lineHeight: 1.05, ...GRADIENT_TITLE }}>
          {slide.title}
        </div>
        {slide.url && (
          <div style={{ fontSize: 50, fontWeight: 700, color: TEXT }}>{slide.url}</div>
        )}
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 6 }}>
          {(slide.badges ?? []).map((repo) => (
            <div
              key={repo.name}
              style={{
                padding: "12px 24px",
                borderRadius: 12,
                background: "rgba(255,255,255,0.05)",
                border: `1px solid ${repo.color}`,
                color: repo.color,
                fontSize: 24,
                fontFamily: "Consolas, monospace",
                fontWeight: 700,
                boxShadow: `0 0 18px ${repo.color}33`,
              }}
            >
              {repo.name}
            </div>
          ))}
        </div>
        {slide.tagline && (
          <div style={{ fontSize: 28, color: MUTED, marginTop: 10 }}>{slide.tagline}</div>
        )}
      </div>
      <div style={{ flex: 0.7, display: "flex", justifyContent: "center" }}>
        <Cube3D size={210} faces={slide.cube_faces} />
      </div>
    </div>
  );
};

const ProgressBar: React.FC = () => {
  const frame = useCurrentFrame();
  const pct = (frame / Math.max(1, DURATION)) * 100;
  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        bottom: 0,
        height: 7,
        background: "rgba(255,255,255,0.08)",
      }}
    >
      <div
        style={{
          width: `${pct}%`,
          height: "100%",
          background: `linear-gradient(90deg, ${CYAN}, ${BLUE}, ${VIOLET}, ${PINK})`,
          boxShadow: `0 0 16px ${CYAN}`,
        }}
      />
    </div>
  );
};

export const DupPresenter: React.FC<Props> = () => {
  let offset = 0;
  return (
    <AbsoluteFill style={{ backgroundColor: BG }}>
      <Aurora3DBackdrop />
      <Audio
        src={staticFile(DECK.ambient_file)}
        volume={DECK.voice?.ambient_volume ?? 0.16}
      />
      {DECK.slides.map((slide) => {
        const from = offset * FPS;
        const durationInFrames = slide.duration_sec * FPS;
        offset += slide.duration_sec;

        let body: React.ReactNode = null;
        if (slide.type === "hero_3d") body = <Hero3DSlide slide={slide} />;
        else if (slide.type === "code_split") body = <CodeSplitSlide slide={slide} />;
        else if (slide.type === "screen_split")
          body = <ScreenSplitSlide slide={slide} dur={durationInFrames} />;
        else if (slide.type === "outro_3d") body = <Outro3DSlide slide={slide} />;

        return (
          <Sequence key={slide.id} from={from} durationInFrames={durationInFrames}>
            <SlideChrome
              brand={DECK.brand}
              num={slide.num}
              tag={slide.tag}
              dur={durationInFrames}
            >
              {body}
            </SlideChrome>
            <Audio src={staticFile(slide.voice_file)} startFrom={0} />
          </Sequence>
        );
      })}
      <ProgressBar />
    </AbsoluteFill>
  );
};

export const DupPresenterComposition = () => {
  return (
    <Composition
      id="DupPresenter"
      component={DupPresenter}
      durationInFrames={DURATION}
      fps={FPS}
      width={DECK.width || 1920}
      height={DECK.height || 1080}
      calculateMetadata={calculateMetadata}
    />
  );
};
