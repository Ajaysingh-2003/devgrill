"use client";

import {
  answerCard,
  calibrationDeck,
  finishOnboarding,
  patchMe,
  type ExperienceLevel,
  type OnboardingOut,
  type QuickfireAnswerIn,
  type QuickfireAnswerOut,
  type QuickfireCardOut,
} from "@devgrill/api-client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import { QuickFireCard } from "@/components/quickfire-card";
import { ProblemError, browserApi, call } from "@/lib/browser-api";

type JobRole = NonNullable<OnboardingOut["me"]["prefs"]["job_role"]>;

const EXPERIENCE: { value: ExperienceLevel; label: string }[] = [
  { value: "student", label: "Still studying" },
  { value: "0-2", label: "Under 2 years" },
  { value: "2-5", label: "2 to 5 years" },
  { value: "5+", label: "More than 5 years" },
];

const ROLES: { value: JobRole; label: string }[] = [
  { value: "backend", label: "Backend" },
  { value: "sre", label: "SRE or platform" },
  { value: "frontend", label: "Frontend or full stack" },
  { value: "data", label: "Data" },
  { value: "student", label: "Student" },
  { value: "other", label: "Something else" },
];

type Step = "about" | "offer" | "cards" | "done";

function Choices<T extends string>({
  legend,
  name,
  options,
  value,
  onChange,
}: {
  legend: string;
  name: string;
  options: { value: T; label: string }[];
  value: T | null;
  onChange: (value: T) => void;
}) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1 text-body font-semibold text-fg">{legend}</legend>
      <div className="grid gap-2 sm:grid-cols-2">
        {options.map((o) => (
          <label
            key={o.value}
            className="flex min-h-11 cursor-pointer items-center gap-3 rounded-sm border border-border-input px-3 py-2 text-body text-fg hover:bg-raised has-checked:border-fg has-checked:bg-raised"
          >
            <input
              type="radio"
              name={name}
              value={o.value}
              checked={value === o.value}
              onChange={() => onChange(o.value)}
              className="size-4 accent-brand"
            />
            {o.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export function OnboardingFlow({
  next,
  name,
  experience: initialExperience,
  role: initialRole,
}: {
  next: string;
  name: string;
  experience: ExperienceLevel | null;
  role: JobRole | null;
}) {
  const router = useRouter();
  const headingId = useId();
  const [step, setStep] = useState<Step>("about");
  const [experience, setExperience] = useState(initialExperience);
  const [role, setRole] = useState(initialRole);
  const [cards, setCards] = useState<QuickfireCardOut[]>([]);
  const [index, setIndex] = useState(0);
  const [picked, setPicked] = useState<string | null>(null);
  const [result, setResult] = useState<QuickfireAnswerOut | null>(null);
  const [answers, setAnswers] = useState<{ card_id: string; choice: QuickfireAnswerIn["choice"] }[]>([]);
  const [outcome, setOutcome] = useState<OnboardingOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // Each step replaces the page's content: move focus to its heading (not on first load).
  const moved = useRef(false);
  useEffect(() => {
    if (moved.current) document.getElementById(headingId)?.focus();
    moved.current = true;
  }, [step, headingId]);

  async function run<T>(work: () => Promise<T>): Promise<T | null> {
    setBusy(true);
    setError("");
    try {
      return await work();
    } catch (err) {
      setError(err instanceof ProblemError ? err.message : "Something went wrong. Try again.");
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function skipAll() {
    const ok = await run(() => call(patchMe({ client: browserApi(), body: { prefs: { onboarded: true } } })));
    if (ok) router.push(next);
  }

  async function finish(given: typeof answers) {
    if (!experience) return;
    const out = await run(() =>
      call(
        finishOnboarding({
          client: browserApi(),
          body: { experience_level: experience, job_role: role, answers: given },
        }),
      ),
    );
    if (out) {
      setOutcome(out);
      setStep("done");
    }
  }

  async function startCards() {
    const deck = await run(() => call(calibrationDeck({ client: browserApi() })));
    if (!deck) return;
    if (!deck.cards.length) return void finish([]);
    setCards(deck.cards);
    setStep("cards");
  }

  async function pick(key: string) {
    const card = cards[index];
    if (!card || result) return;
    setPicked(key);
    const choice = key as QuickfireAnswerIn["choice"];
    const out = await run(() =>
      call(answerCard({ client: browserApi(), path: { card_id: card.id }, body: { choice } })),
    );
    if (!out) return setPicked(null);
    setResult(out);
    setAnswers((a) => [...a, { card_id: card.id, choice }]);
  }

  function nextCard() {
    if (index + 1 >= cards.length) return void finish(answers);
    setIndex((i) => i + 1);
    setPicked(null);
    setResult(null);
  }

  const errorLine = error ? (
    <p role="alert" className="text-body text-danger-text">
      {error}
    </p>
  ) : null;

  if (step === "about") {
    return (
      <section aria-labelledby={headingId} className="flex flex-col gap-6">
        <div className="flex flex-col gap-2">
          <h1 id={headingId} tabIndex={-1} className="text-heading-lg font-semibold tracking-tight text-fg">
            Welcome, {name}
          </h1>
          <p className="text-body-lg text-fg-muted">
            Two questions so the first drills fit you. You can change these later.
          </p>
        </div>
        <Choices
          legend="How long have you worked on production systems?"
          name="experience"
          options={EXPERIENCE}
          value={experience}
          onChange={setExperience}
        />
        <Choices
          legend="What do you mostly work on?"
          name="role"
          options={ROLES}
          value={role}
          onChange={setRole}
        />
        {errorLine}
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            disabled={!experience || busy}
            onClick={() => setStep("offer")}
            className="inline-flex h-10 items-center rounded-sm bg-brand px-4 text-body font-semibold text-on-brand hover:bg-brand-hover disabled:opacity-50"
          >
            Continue
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void skipAll()}
            className="inline-flex h-10 items-center rounded-sm px-3 text-body font-medium text-fg-muted hover:bg-raised hover:text-fg"
          >
            Skip for now
          </button>
        </div>
      </section>
    );
  }

  if (step === "offer") {
    return (
      <section aria-labelledby={headingId} className="flex flex-col gap-5">
        <h1 id={headingId} tabIndex={-1} className="text-heading-lg font-semibold tracking-tight text-fg">
          Want a better starting point?
        </h1>
        <p className="max-w-xl text-body-lg text-fg-muted">
          Answer six Quick Fire cards, one for each track. It takes about two minutes. Your answers set where
          each track starts, and your first drills fine-tune it from there.
        </p>
        {errorLine}
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            disabled={busy}
            onClick={() => void startCards()}
            className="inline-flex h-10 items-center rounded-sm bg-brand px-4 text-body font-semibold text-on-brand hover:bg-brand-hover disabled:opacity-60"
          >
            Answer six cards
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void finish([])}
            className="inline-flex h-10 items-center rounded-sm px-3 text-body font-medium text-fg-muted hover:bg-raised hover:text-fg"
          >
            Skip the cards
          </button>
        </div>
      </section>
    );
  }

  if (step === "cards") {
    const card = cards[index]!;
    return (
      <section aria-label="Calibration" className="flex flex-col gap-4">
        <p id={headingId} tabIndex={-1} className="text-label text-fg-muted">
          Card {index + 1} of {cards.length}
        </p>
        <QuickFireCard card={card} picked={picked} result={result} busy={busy} onPick={(k) => void pick(k)} />
        {errorLine}
        {result ? (
          <button
            type="button"
            disabled={busy}
            onClick={nextCard}
            className="inline-flex h-10 w-fit items-center rounded-sm bg-brand px-4 text-body font-semibold text-on-brand hover:bg-brand-hover disabled:opacity-60"
          >
            {index + 1 >= cards.length ? "Finish" : "Next card"}
          </button>
        ) : null}
      </section>
    );
  }

  const right = outcome?.results.filter((r) => r.correct).length ?? 0;
  const total = outcome?.results.length ?? 0;
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-5">
      <h1 id={headingId} tabIndex={-1} className="text-heading-lg font-semibold tracking-tight text-fg">
        You’re set
      </h1>
      <p className="max-w-xl text-body-lg text-fg-muted">
        {total
          ? `${right} of ${total} right. That sets where each track starts; your first drills will tune it.`
          : "Your first drills will set where each track starts."}{" "}
        A good first one is a SEV4 warm-up.
      </p>
      <Link
        href={next}
        className="inline-flex h-10 w-fit items-center rounded-sm bg-brand px-4 text-body font-semibold text-on-brand hover:bg-brand-hover"
      >
        Pick your first drill
      </Link>
    </section>
  );
}
