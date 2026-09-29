/** Query-building for the library list. Kept pure so it can be unit tested. */

export const SORTS = {
  newest: "p.created_at DESC",
  oldest: "p.created_at ASC",
  edited: "p.updated_at DESC",
  name: "lower(p.title) ASC",
  length: "p.target_length_min DESC NULLS LAST",
} as const;

export type SortKey = keyof typeof SORTS;

export const STATUSES = ["draft", "approved", "exported", "archived"] as const;
export type Status = (typeof STATUSES)[number];

export function parseSort(value: string | undefined): SortKey {
  return value && value in SORTS ? (value as SortKey) : "newest";
}

export function parseStatus(value: string | undefined): Status | null {
  return (STATUSES as readonly string[]).includes(value ?? "") ? (value as Status) : null;
}

/** Escape LIKE wildcards so user input is matched literally. */
export function escapeLike(input: string): string {
  return input.replace(/[\\%_]/g, (c) => `\\${c}`);
}

export function buildLibraryQuery(sort: SortKey, status: Status | null, q: string) {
  // ORDER BY comes from the SORTS whitelist only; user input is never interpolated.
  const sql = `
    SELECT p.id, p.title, p.intent, p.mood, p.status, p.is_favorite, p.source_profile_id,
           p.target_length_min, p.created_at, p.updated_at,
           (SELECT count(*)::int FROM playlist_tracks t
             WHERE t.version_id = (SELECT v.id FROM playlist_versions v
                                    WHERE v.playlist_id = p.id
                                    ORDER BY v.version_no DESC LIMIT 1)) AS track_count
      FROM playlists p
     WHERE ($1::playlist_status IS NULL OR p.status = $1::playlist_status)
       AND ($2::text = '' OR p.title ILIKE '%' || $2 || '%' ESCAPE '\\')
     ORDER BY p.is_favorite DESC, ${SORTS[sort]}
  `;
  return { sql, params: [status, escapeLike(q.trim())] };
}
