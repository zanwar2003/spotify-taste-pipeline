import Link from "next/link";
import { redirect } from "next/navigation";
import { withUser } from "@/lib/db";
import { buildLibraryQuery, parseSort, parseStatus, STATUSES } from "@/lib/library";
import { getSessionUserId } from "@/lib/session";

export const dynamic = "force-dynamic";

type Row = {
  id: string;
  title: string;
  intent: string | null;
  mood: string | null;
  status: string;
  is_favorite: boolean;
  source_profile_id: string | null;
  target_length_min: number | null;
  track_count: number;
  created_at: Date;
};

export default async function LibraryPage({
  searchParams,
}: {
  searchParams: Promise<{ sort?: string; status?: string; q?: string }>;
}) {
  const userId = await getSessionUserId();
  if (!userId) redirect("/");

  const { sort, status, q } = await searchParams;
  const sortKey = parseSort(sort);
  const statusFilter = parseStatus(status);
  const query = (q ?? "").slice(0, 100);

  const { sql, params } = buildLibraryQuery(sortKey, statusFilter, query);
  const rows = await withUser(userId, async (db) => (await db.query<Row>(sql, params)).rows);
  const filtered = statusFilter !== null || query !== "";

  return (
    <>
      <h1>Your library</h1>
      <p className="lede">Every playlist you've built. Reopen one to keep refining it.</p>

      <form className="filters" method="get" role="search" aria-label="Filter playlists">
        <label className="sr-only" htmlFor="q">Search by name</label>
        <input id="q" name="q" type="search" placeholder="Search by name" defaultValue={query} />
        <label className="sr-only" htmlFor="status">Status</label>
        <select id="status" name="status" defaultValue={statusFilter ?? ""}>
          <option value="">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>{s[0].toUpperCase() + s.slice(1)}</option>
          ))}
        </select>
        <label className="sr-only" htmlFor="sort">Sort by</label>
        <select id="sort" name="sort" defaultValue={sortKey}>
          <option value="newest">Newest first</option>
          <option value="oldest">Oldest first</option>
          <option value="edited">Recently edited</option>
          <option value="name">Name</option>
          <option value="length">Longest</option>
        </select>
        <button className="btn secondary" type="submit">Apply</button>
      </form>

      {rows.length === 0 ? (
        <div className="empty">
          <h2>{filtered ? "No playlists match" : "No playlists yet"}</h2>
          <p>{filtered ? "Try clearing your filters." : "Build your first playlist to see it here."}</p>
          <Link className="btn" href={filtered ? "/library" : "/build"}>
            {filtered ? "Clear filters" : "Build a playlist"}
          </Link>
        </div>
      ) : (
        <ul className="cards">
          {rows.map((p) => (
            <li key={p.id} className="card">
              <h3>{p.is_favorite && <span aria-label="Favorite">★ </span>}{p.title}</h3>
              <p className="meta">
                <span className="badge">{p.status}</span>
                {[p.mood, p.intent, p.source_profile_id && `from ${p.source_profile_id}`]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
              <p className="meta">
                {p.track_count} tracks
                {p.target_length_min ? ` · ${p.target_length_min} min target` : ""} ·{" "}
                {new Date(p.created_at).toLocaleDateString("en-US", { dateStyle: "medium" })}
              </p>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
