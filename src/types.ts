import type { ThemeId } from "./themes";

export interface PillItem {
  name: string;
  color: string;
}

export interface BulletData {
  title: string;
  desc: string;
  accent?: string;
}

export interface CodeLine {
  text: string;
  color?: string;
}

export interface ScreenFocus {
  x: number;
  y: number;
  zoom?: number;
}

export interface ScreenItem {
  src: string;
  caption: string;
  focus?: ScreenFocus;
}

export interface ArchNode {
  id: string;
  label: string;
  path?: string;
  layer?: number;
}

export interface ArchEdge {
  from: string;
  to: string;
  label?: string;
}

export interface KpiItem {
  value: string;
  label: string;
}

export interface CaptionWord {
  w: string;
  start: number;
  end: number;
}

export interface CaptionCue {
  start_sec: number;
  end_sec: number;
  text: string;
  speaker?: string;
  words?: CaptionWord[];
}

export interface StockMedia {
  video_file: string;
  credit: string;
  credit_url: string;
  provider: "pexels" | "pixabay";
  query: string;
}

export interface ResolvedSlide {
  id: string;
  num: string;
  tag: string;
  type: "hero_3d" | "code_split" | "screen_split" | "arch_flow" | "outro_3d" | "timeline" | "terminal" | "kpi";
  duration_sec: number;
  start_sec?: number;
  voice_delay_sec?: number;
  speech_windows?: [number, number][];
  voice_file: string;
  background_query?: string;
  media?: StockMedia;
  title: string;
  subtitle?: string;
  url?: string;
  tagline?: string;
  pills?: PillItem[];
  badges?: PillItem[];
  cube_faces?: string[];
  bullets?: BulletData[];
  code?: {
    filename: string;
    lines: CodeLine[];
  };
  screens?: ScreenItem[];
  arch?: {
    nodes: ArchNode[];
    edges: ArchEdge[];
  };
  kpis?: KpiItem[];
  captions?: CaptionCue[];
}

export interface ResolvedDeck {
  slug: string;
  lang?: "ru" | "en";
  theme?: ThemeId;
  aspect?: "16:9" | "9:16";
  burn_captions?: boolean;
  brand: string;
  fps: number;
  width: number;
  height: number;
  total_seconds: number;
  total_frames?: number;
  transition_style?: "fade" | "slide" | "wipe" | "none";
  transition_frames?: number;
  ambient_file: string;
  music_file?: string;
  music_volume?: number;
  music_duck_ratio?: number;
  sfx_enabled?: boolean;
  sfx_volume?: number;
  sfx_transition_file?: string;
  sfx_pop_file?: string;
  bg_code_streams?: string[][];
  voice: {
    engine: string;
    lang?: string;
    mode?: "single" | "podcast";
    speaker: string;
    speaker_b?: string;
    rate: string;
    ambient_volume: number;
  };
  slides: ResolvedSlide[];
}
