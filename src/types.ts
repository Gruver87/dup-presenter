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

export interface LedgerLayerItem {
  id: string;
  name: string;
  tech: string;
  desc: string;
  guarantee: string;
  accent?: string;
}

export interface JourneyBlock {
  height: string;
  hash: string;
  tx_count: string;
  sealed?: boolean;
}

export interface JourneyStep {
  title: string;
  badge: string;
  detail: string;
  accent?: string;
}

export interface TxJourneyData {
  tx_label: string;
  amount_label: string;
  signature_label: string;
  merkle_leaves?: string[];
  blocks: JourneyBlock[];
  steps: JourneyStep[];
}

export interface MeshNodeItem {
  id: string;
  role: string;
  endpoint: string;
  status: string;
  height?: string;
}

export interface MeshNetworkData {
  protocol_label: string;
  chain_id: string;
  probe_label: string;
  nodes: MeshNodeItem[];
  recovery_steps: BulletData[];
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
  type:
    | "hero_3d"
    | "code_split"
    | "screen_split"
    | "ui_recording"
    | "arch_flow"
    | "outro_3d"
    | "timeline"
    | "terminal"
    | "kpi"
    | "quote"
    | "ledger_layers"
    | "tx_journey"
    | "mesh_network";
  // quote: title = the quote text (<= 220 chars), subtitle = attribution (optional)
  // ui_recording: MP4 from scripts/record_ui.py under public/ui_recordings/ (played muted inside the 3D frame)
  recording?: { src: string; caption?: string; focus?: ScreenFocus; duration_sec?: number };
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
  layers?: LedgerLayerItem[];
  journey?: TxJourneyData;
  mesh?: MeshNetworkData;
  captions?: CaptionCue[];
}

export interface ResolvedDeck {
  slug: string;
  lang?: "ru" | "en";
  theme?: ThemeId;
  aspect?: "16:9" | "9:16";
  burn_captions?: boolean;
  // box = boxed cue (default); karaoke = word-by-word highlight from word timings; bold = large text, no box.
  caption_style?: "box" | "karaoke" | "bold";
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
