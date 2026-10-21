export interface MontageOverlayLayer {
  id: string;
  name: string;
  enabled: boolean;
  path: string;
  kind: "image" | "video";
  x: number;
  y: number;
  width: number;
  height: number;
  keepAspect: boolean;
  opacity: number;
  start: number;
  duration: number;
  mode: "once" | "repeat" | "end" | "until-end" | "intervals" | "count";
  ranges?: Array<{ start: number; end: number }>;
  repeatCount?: number;
  rangeEnd?: number | null;
  repeatEvery: number;
  endOffset: number;
  chromaEnabled: boolean;
  chromaColor: string;
  chromaSimilarity: number;
  chromaBlend: number;
  audioEnabled: boolean;
  randomGroup?: string;
  librarySourceId?: string;
}

export interface MontageOverlayLibrarySource {
  id: string;
  name: string;
  root: string;
  enabled: boolean;
  mode: "random" | "all";
  kind: "image" | "video" | "all";
}

export interface MontageOverlayTemplate {
  version: 1;
  libraryRoot?: string;
  librarySources?: MontageOverlayLibrarySource[];
  layouts: Record<"16:9" | "9:16", MontageOverlayLayer[]>;
}
