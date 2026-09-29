"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { parseMinutes } from "@/lib/http";
import type { ApiError, PlaylistView } from "@/lib/types";

const STEPS = ["Profile", "Intent", "Mood", "Length", "Review"] as const;
type AskStep = "Profile" | "Intent" | "Mood" | "Length";

const QUESTIONS: Record<AskStep, { ask: string; chips?: { label: string; value: string }[]; placeholder: string }> = {
  Profile: { ask: "Whose public Spotify profile should I use? Enter their username.", placeholder: "Spotify username" },
  Intent: {
    ask: "What's the playlist for?",
    chips: ["Workout", "Focus", "Road trip", "Party", "Wind down"].map((c) => ({ label: c, value: c })),
    placeholder: "Or type your own",
  },
  Mood: {
    ask: "What mood do you want?",
    chips: ["Upbeat", "Chill", "Moody", "Nostalgic", "Energetic"].map((c) => ({ label: c, value: c })),
    placeholder: "Or type your own",
  },
  Length: {
    ask: "How long should it be?",
    chips: [
      { label: "30 min", value: "30" },
      { label: "1 hour", value: "60" },
      { label: "2 hours", value: "120" },
    ],
    placeholder: "For example 45 min or 1.5 hours",
  },
};
const ORDER: AskStep[] = ["Profile", "Intent", "Mood", "Length"];

const FEEDBACK_CHIPS = ["More upbeat", "Slow it down", "More songs I know", "More new discoveries"];

type Message = { who: "bot" | "user"; text: string };
type Phase = "asking" | "building" | "review" | "refining" | "approved";
type Answers = { profile?: string; intent?: string; mood?: string; minutes?: number };

async function post<T>(url: string, body?: unknown): Promise<{ ok: true; data: T } | { ok: false; error: ApiError }> {
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body ?? {}),
    });
    const json = await res.json().catch(() => null);
    if (res.ok && json) return { ok: true, data: json as T };
    return { ok: false, error: json?.error ?? { code: "unknown", message: "Something went wrong. Please try again." } };
  } catch {
    return { ok: false, error: { code: "network", message: "Couldn't reach the server. Check your connection and try again." } };
  }
}

export function ChatShell() {
  const [messages, setMessages] = useState<Message[]>([{ who: "bot", text: QUESTIONS.Profile.ask }]);
  const [stepIndex, setStepIndex] = useState(0);
  const [answers, setAnswers] = useState<Answers>({});
  const [phase, setPhase] = useState<Phase>("asking");
  const [playlist, setPlaylist] = useState<PlaylistView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);

  const step: AskStep | null = phase === "asking" ? ORDER[stepIndex] : null;
  const busy = phase === "building" || phase === "refining";

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [messages, phase]);

  // Move focus to the playlist when it first appears so keyboard and screen-reader users land on it.
  useEffect(() => {
    if (playlist && phase === "review") headingRef.current?.focus();
  }, [playlist?.id, playlist?.version, phase]); // eslint-disable-line react-hooks/exhaustive-deps

  const say = (...m: Message[]) => setMessages((prev) => [...prev, ...m]);

  async function build(a: Required<Answers>) {
    setPhase("building");
    setError(null);
    const res = await post<PlaylistView>("/api/playlists", {
      source_username: a.profile,
      intent: a.intent,
      mood: a.mood,
      target_minutes: a.minutes,
    });
    if (res.ok) {
      setPlaylist(res.data);
      setPhase("review");
      say({ who: "bot", text: `Here's "${res.data.title}". Want to change anything, or does it look right?` });
    } else if (res.error.code === "no_public_playlists") {
      say({ who: "bot", text: res.error.message }, { who: "bot", text: QUESTIONS.Profile.ask });
      setAnswers((prev) => ({ ...prev, profile: undefined }));
      setStepIndex(0);
      setPhase("asking");
    } else {
      setError(res.error.message);
      setPhase("asking");
      setStepIndex(ORDER.length - 1);
    }
  }

  function answer(raw: string, label?: string) {
    const value = raw.trim();
    if (!value || !step) return;
    let next: Answers = { ...answers };
    if (step === "Length") {
      const minutes = parseMinutes(value);
      if (minutes === null) {
        setError("Enter a length between 1 minute and 8 hours, like 45 min or 1.5 hours.");
        return;
      }
      next = { ...next, minutes };
    } else {
      next = { ...next, [step.toLowerCase()]: value };
    }
    setError(null);
    setText("");
    setAnswers(next);
    say({ who: "user", text: label ?? value });

    if (step === "Length") {
      say({ who: "bot", text: "On it. I'll check their public playlists and build this now. It can take up to a minute." });
      void build(next as Required<Answers>);
    } else {
      const upcoming = ORDER[stepIndex + 1];
      say({ who: "bot", text: QUESTIONS[upcoming].ask });
      setStepIndex(stepIndex + 1);
    }
  }

  async function sendFeedback(message: string) {
    const trimmed = message.trim();
    if (!trimmed || !playlist) return;
    setText("");
    setError(null);
    setPhase("refining");
    say({ who: "user", text: trimmed });
    const res = await post<PlaylistView>(`/api/playlists/${playlist.id}/feedback`, { message: trimmed });
    if (res.ok) {
      setPlaylist(res.data);
      say({ who: "bot", text: res.data.summary || "Updated. How does this look?" });
    } else {
      setError(res.error.message);
    }
    setPhase("review");
  }

  async function approve() {
    if (!playlist) return;
    setError(null);
    const res = await post<PlaylistView>(`/api/playlists/${playlist.id}/approve`);
    if (res.ok) {
      setPlaylist(res.data);
      setPhase("approved");
      say({ who: "bot", text: "Approved. It's saved in your library." });
    } else {
      setError(res.error.message);
    }
  }

  function restart() {
    setMessages([{ who: "bot", text: QUESTIONS.Profile.ask }]);
    setStepIndex(0);
    setAnswers({});
    setPlaylist(null);
    setError(null);
    setPhase("asking");
  }

  const activeStep = phase === "asking" ? stepIndex : 4;
  const q = step ? QUESTIONS[step] : null;

  return (
    <>
      <ol className="steps" aria-label="Progress">
        {STEPS.map((s, i) => (
          <li key={s} className={i < activeStep ? "done" : undefined} aria-current={i === activeStep ? "step" : undefined}>
            {s}
          </li>
        ))}
      </ol>

      <div className="chat-log" role="log" aria-live="polite">
        {/* Once a playlist exists, keep only recent turns so it stays near the top on phones. */}
        {(playlist ? messages.slice(-3) : messages).map((m, i) => (
          <p key={i} className={m.who === "user" ? "msg user" : "msg"}>
            {m.text}
          </p>
        ))}
        <div ref={endRef} />
      </div>

      <div role="status" aria-live="polite">
        {busy && <p className="msg" aria-busy="true">{phase === "building" ? "Building your playlist…" : "Updating your playlist…"}</p>}
      </div>

      {error && <p role="alert" className="alert">{error}</p>}

      {playlist && phase !== "asking" && phase !== "building" && (
        <section className="playlist" aria-labelledby="playlist-title">
          <h2 id="playlist-title" tabIndex={-1} ref={headingRef}>{playlist.title}</h2>
          <p className="meta">
            <span className="badge">{playlist.status}</span>
            Version {playlist.version} · {playlist.tracks.length} songs · {playlist.total_minutes} of {playlist.target_minutes} min
          </p>

          {(playlist.added.length > 0 || playlist.removed.length > 0) && playlist.version > 1 && (
            <div className="diff" aria-label="What changed">
              {playlist.removed.length > 0 && <p><strong>Removed:</strong> {playlist.removed.join("; ")}</p>}
              {playlist.added.length > 0 && <p><strong>Added:</strong> {playlist.added.join("; ")}</p>}
            </div>
          )}
          {playlist.notes.map((n) => <p key={n} className="note">{n}</p>)}

          <ol className="tracks">
            {playlist.tracks.map((t) => (
              <li key={t.spotify_track_id}>
                <span className="track-name">{t.artist} – {t.title}</span>
                {t.origin === "reference" && <span className="badge">From reference</span>}
                {t.reason && <span className="reason">{t.reason}</span>}
              </li>
            ))}
          </ol>
        </section>
      )}

      {q && (
        <>
          {q.chips && (
            <div className="chips" role="group" aria-label="Quick replies">
              {q.chips.map((c) => (
                <button key={c.label} type="button" className="chip" onClick={() => answer(c.value, c.label)}>
                  {c.label}
                </button>
              ))}
            </div>
          )}
          <form className="field" onSubmit={(e) => { e.preventDefault(); answer(text); }}>
            <label htmlFor="chat-input" className="sr-only">{q.ask}</label>
            <input id="chat-input" value={text} onChange={(e) => setText(e.target.value)} placeholder={q.placeholder} autoComplete="off" autoCapitalize="none" />
            <button type="submit" className="btn" disabled={!text.trim()}>Send</button>
          </form>
        </>
      )}

      {(phase === "review" || phase === "refining") && (
        <>
          <div className="chips" role="group" aria-label="Suggested changes">
            {FEEDBACK_CHIPS.map((c) => (
              <button key={c} type="button" className="chip" disabled={busy} onClick={() => void sendFeedback(c)}>
                {c}
              </button>
            ))}
          </div>
          <form className="field" onSubmit={(e) => { e.preventDefault(); void sendFeedback(text); }}>
            <label htmlFor="feedback-input" className="sr-only">Describe what to change</label>
            <input
              id="feedback-input" value={text} maxLength={500} disabled={busy}
              onChange={(e) => setText(e.target.value)}
              placeholder="Ask for a change"
              autoComplete="off"
            />
            <button type="submit" className="btn secondary" disabled={busy || !text.trim()}>Change it</button>
          </form>
          <p className="actions">
            <button type="button" className="btn" disabled={busy} onClick={() => void approve()}>Approve playlist</button>
          </p>
        </>
      )}

      {phase === "approved" && (
        <p className="actions">
          <Link className="btn" href="/library">View your library</Link>
          <button type="button" className="btn secondary" onClick={restart}>Build another</button>
        </p>
      )}
    </>
  );
}
