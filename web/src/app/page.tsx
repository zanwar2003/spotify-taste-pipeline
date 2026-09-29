import { redirect } from "next/navigation";
import { getSessionUserId } from "@/lib/session";

export const dynamic = "force-dynamic";

const ERRORS: Record<string, string> = {
  denied: "Spotify sign-in was cancelled. Connect again when you're ready.",
  state: "That sign-in link expired. Try connecting again.",
  server: "We couldn't finish signing you in. Please try again.",
};

export default async function Home({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  if (await getSessionUserId()) redirect("/build");
  const { error } = await searchParams;

  return (
    <>
      <h1>Build a playlist from someone's public Spotify profile</h1>
      <p className="lede">
        Connect Spotify, give us a username, and tell us the mood. Your playlists are saved in your library.
      </p>
      {error && ERRORS[error] && <p role="alert" className="alert">{ERRORS[error]}</p>}
      <a className="btn" href="/api/auth/login">Connect Spotify</a>
    </>
  );
}
