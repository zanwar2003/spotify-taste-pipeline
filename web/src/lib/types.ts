export type ViewTrack = {
  position: number;
  spotify_track_id: string;
  title: string;
  artist: string;
  duration_ms: number;
  reason: string;
  origin: string | null;
};

/** Mirrors the agent API's PlaylistView. */
export type PlaylistView = {
  id: string;
  title: string;
  status: "draft" | "approved" | "exported" | "archived";
  version: number;
  target_minutes: number;
  total_minutes: number;
  tracks: ViewTrack[];
  summary: string;
  added: string[];
  removed: string[];
  notes: string[];
};

export type ApiError = { code: string; message: string };
