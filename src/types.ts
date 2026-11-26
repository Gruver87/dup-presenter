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

export interface CosmosStationItem {
  id: string;
  side: "left" | "right";
  badge: string;
  title: string;
  detail: string;
  metric: string;
  color: string;
  role?: "shield" | "flow" | "verify";
}

export interface ProtocolCosmosData {
  core_title: string;
  core_subtitle: string;
  core_badges: string[];
  stations: CosmosStationItem[];
}

export interface VersusSide {
  label: string;
  badge?: string;
  points: string[];
  accent?: string;
}

export interface VersusSplitData {
  left: VersusSide;
  right: VersusSide;
  verdict?: string;
}

export interface ChartSeriesItem {
  label: string;
  value: number;
  display?: string;
  color?: string;
}

export interface ChartStoryData {
  kind: "bar" | "line" | "donut";
  unit?: string;
  source_note?: string;
  series: ChartSeriesItem[];
}

export interface StatBurstData {
  headline: string;
  kicker?: string;
  caption: string;
  chips?: { label: string; color?: string }[];
}

export interface BRollCinematicData {
  image?: string;
  badge?: string;
  caption?: string;
  callouts?: string[];
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

export interface CinemaClipData {
  src?: string;
  badge?: string;
  caption?: string;
  loop?: boolean;
  zoom?: number;
  clip_duration_sec?: number;
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
    | "mesh_network"
    | "protocol_cosmos"
    | "versus_split"
    | "chart_story"
    | "stat_burst"
    | "broll_cinematic"
    | "cinema_clip";
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
  cosmos?: ProtocolCosmosData;
  versus?: VersusSplitData;
  chart?: ChartStoryData;
  stat_burst?: StatBurstData;
  broll?: BRollCinematicData;
  cinema?: CinemaClipData;
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
