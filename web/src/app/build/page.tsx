import { redirect } from "next/navigation";
import { ChatShell } from "@/components/ChatShell";
import { getSessionUserId } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function BuildPage() {
  if (!(await getSessionUserId())) redirect("/");
  return (
    <>
      <h1>Build a playlist</h1>
      <p className="lede">Answer a few quick questions and we'll build it from their public playlists.</p>
      <ChatShell />
    </>
  );
}
