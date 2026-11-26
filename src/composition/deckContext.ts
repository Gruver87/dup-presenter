import type React from "react";
import { resolveTheme } from "../themes";
import { ResolvedDeck } from "../types";
import rawDeck from "../generated/deck_resolved.json";

export const DECK = rawDeck as unknown as ResolvedDeck;

export const THEME = resolveTheme(DECK.theme);

export const FPS = DECK.fps || 30;

export const WIDTH = DECK.width || 1920;

export const HEIGHT = DECK.height || 1080;

export const IS_PORTRAIT = HEIGHT > WIDTH;

export const TRANSITION_STYLE = DECK.transition_style ?? "fade";

export const TRANSITION_FRAMES =
  TRANSITION_STYLE === "none" || DECK.slides.length < 2
    ? 0
    : Math.max(0, Math.min(24, DECK.transition_frames ?? 12));

export const COMPUTED_TOTAL_FRAMES =
  DECK.slides.reduce((acc, s) => acc + Math.max(1, Math.round(s.duration_sec * FPS)), 0) -
  Math.max(0, DECK.slides.length - 1) * TRANSITION_FRAMES;

export const DURATION = Math.max(1, DECK.total_frames ?? COMPUTED_TOTAL_FRAMES);

// Precompute global [startSec, endSec] speech intervals across all slides for smooth music ducking.

export const GLOBAL_SPEECH_WINDOWS: [number, number][] = (() => {
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

export const computeDuckFactor = (frame: number, duckRatio: number): number => {
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

export const BG = THEME.bg;

export const CYAN = THEME.accent1;

export const BLUE = THEME.accent2;

export const VIOLET = THEME.accent3;

export const PINK = THEME.accent4;

export const TEXT = THEME.text;

export const MUTED = THEME.muted;

export const IS_COSMIC = THEME.id === "cosmic_radar";

export const IS_QUANTUM = THEME.id === "quantum_ledger";

export const IS_LIGHT = THEME.id === "minimal_light" || THEME.id === "paper_warm" || THEME.id === "corporate_blue";

export const GRADIENT_TITLE: React.CSSProperties = {
  background: IS_COSMIC
    ? `linear-gradient(100deg, #ffffff 0%, ${CYAN} 32%, ${BLUE} 68%, ${VIOLET} 100%)`
    : `linear-gradient(95deg, ${CYAN} 0%, ${BLUE} 48%, ${VIOLET} 100%)`,
  WebkitBackgroundClip: "text",
  WebkitTextFillColor: "transparent",
};

// 3D lifted/embossed gradient title: extrusion shadow layer beneath + bright high-contrast gradient face on top
