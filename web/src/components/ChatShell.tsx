"use client";

import { useEffect, useRef, useState } from "react";

// Phase 1 shell: collects the answers the agent will use in Phase 4. No backend calls yet.
const STEPS = ["Profile", "Intent", "Mood", "Length", "Review"] as const;
type Step = (typeof STEPS)[number];

const QUESTIONS: Record<Exclude<Step, "Review">, { ask: string; chips?: string[] }> = {
  Profile: { ask: "Whose public Spotify profile should I use? Enter their username." },
  Intent: {
    ask: "What's the playlist for?",
    chips: ["Workout", "Focus", "Road trip", "Party", "Wind down"],
  },
  Mood: {
    ask: "What mood do you want?",
    chips: ["Upbeat", "Chill", "Moody", "Nostalgic", "Energetic"],
  },
  Length: { ask: "How long should it be?", chips: ["30 min", "1 hour", "2 hours"] },
};

type Answers = Partial<Record<Exclude<Step, "Review">, string>>;

export function ChatShell() {
  const [stepIndex, setStepIndex] = useState(0);
  const [answers, setAnswers] = useState<Answers>({});
  const [text, setText] = useState("");
  const logEndRef = useRef<HTMLDivElement>(null);

  const step = STEPS[stepIndex];
  const question = step === "Review" ? null : QUESTIONS[step];

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ block: "nearest" });
  }, [stepIndex]);

  function answer(value: string) {
    const v = value.trim();
    if (!v || step === "Review") return;
    setAnswers((a) => ({ ...a, [step]: v }));
    setStepIndex((i) => i + 1);
    setText("");
  }

  function restart() {
    setAnswers({});
    setStepIndex(0);
  }

  return (
    <>
      <ol className="steps" aria-label="Progress">
        {STEPS.map((s, i) => (
          <li key={s} className={i < stepIndex ? "done" : undefined} aria-current={i === stepIndex ? "step" : undefined}>
            {s}
          </li>
        ))}
      </ol>

      {/* Live region so screen readers announce each new message */}
      <div className="chat-log" role="log" aria-live="polite">
        {(Object.keys(QUESTIONS) as (keyof typeof QUESTIONS)[]).slice(0, stepIndex + 1).map((key) => (
          <div key={key} style={{ display: "contents" }}>
            <p className="msg">{QUESTIONS[key].ask}</p>
            {answers[key] && <p className="msg user">{answers[key]}</p>}
          </div>
        ))}
        {step === "Review" && (
          <p className="msg">
            Got it: a {answers.Mood?.toLowerCase()} {answers.Intent?.toLowerCase()} playlist of about{" "}
            {answers.Length} from {answers.Profile}'s public playlists. Generation is coming in a later
            phase, so nothing is created yet.
          </p>
        )}
        <div ref={logEndRef} />
      </div>

      {question?.chips && (
        <div className="chips" role="group" aria-label="Quick replies">
          {question.chips.map((c) => (
            <button key={c} type="button" className="chip" onClick={() => answer(c)}>
              {c}
            </button>
          ))}
        </div>
      )}

      {question && (
        <form
          className="field"
          onSubmit={(e) => {
            e.preventDefault();
            answer(text);
          }}
        >
          <label htmlFor="chat-input" className="sr-only">
            {question.ask}
          </label>
          <input
            id="chat-input"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={step === "Profile" ? "Spotify username" : "Or type your own"}
            autoComplete="off"
            autoCapitalize="none"
          />
          <button type="submit" className="btn" disabled={!text.trim()}>
            Send
          </button>
        </form>
      )}

      {step === "Review" && (
        <button type="button" className="btn secondary" onClick={restart}>
          Start over
        </button>
      )}
    </>
  );
}
