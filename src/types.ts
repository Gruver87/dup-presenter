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

export interface ScreenItem {
  src: string;
  caption: string;
}

export interface ResolvedSlide {
  id: string;
  num: string;
  tag: string;
  type: "hero_3d" | "code_split" | "screen_split" | "outro_3d";
  duration_sec: number;
  voice_file: string;
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
}

export interface ResolvedDeck {
  slug: string;
  brand: string;
  fps: number;
  width: number;
  height: number;
  total_seconds: number;
  ambient_file: string;
  voice: {
    engine: string;
    speaker: string;
    rate: string;
    ambient_volume: number;
  };
  slides: ResolvedSlide[];
}
