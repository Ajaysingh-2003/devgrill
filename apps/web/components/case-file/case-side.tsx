"use client";

import {
  answerCaseFile,
  reviewCaseFile,
  type CaseFileOut,
  type CaseQuestionOut,
  type CaseResultOut,
} from "@devgrill/api-client";
import { CircleCheck, CircleX } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@devgrill/ui/components/ui/tabs";
import { browserApi, call } from "@/lib/browser-api";
import { useAction } from "../workspace/context";
import { sinceStart } from "../workspace/model";

const PANEL_LABEL: Record<string, string> = {
  deploys: "Deploys",
  logs: "Logs",
  database: "Database",
  cache: "Cache",
  code: "Code",
  commands: "Commands",
};
const SHORT: Record<string, string> = { root_cause: "The cause", mitigation: "First move", fix: "The fix" };

/** The side panel: your findings, and what the team was saying while it happened. */
export function CaseSide({ file, onPanel }: { file: CaseFileOut; onPanel: (panel: string) => void }) {
  return (
    <Tabs defaultValue="findings" className="flex h-full min-h-0 flex-col bg-surface">
      <TabsList className="shrink-0 border-b border-border">
        <TabsTrigger value="findings">Your findings</TabsTrigger>
        <TabsTrigger value="team">Team chat</TabsTrigger>
      </TabsList>
      <TabsContent value="findings" className="min-h-0 flex-1 overflow-y-auto">
        <Findings file={file} onPanel={onPanel} />
      </TabsContent>
      <TabsContent value="team" className="min-h-0 flex-1 overflow-y-auto">
        <ol className="flex flex-col gap-3 p-3">
          {file.beats.map((b) => (
            <li key={`${b.at_s}-${b.persona}`} className="text-body text-fg">
              <p className="text-label font-semibold text-fg-muted capitalize">
                {b.persona}{" "}
                <span className="font-mono font-normal text-fg-subtle">+{sinceStart(b.at_s * 1000, 0)}</span>
              </p>
              <p>{b.say}</p>
            </li>
          ))}
        </ol>
      </TabsContent>
    </Tabs>
  );
}

function Findings({ file, onPanel }: { file: CaseFileOut; onPanel: (panel: string) => void }) {
  const [result, setResult] = useState<CaseResultOut | null>(file.result ?? null);
  const [choices, setChoices] = useState<Record<string, string>>({});
  const submit = useAction(async () => {
    const out = await call(
      answerCaseFile({
        client: browserApi(),
        path: { slug: file.slug },
        body: {
          root_cause: choices.root_cause as "a",
          mitigation: choices.mitigation as "a",
          fix: choices.fix as "a",
        },
      }),
    );
    setResult(out);
  });
  const ready = file.questions.every((q) => choices[q.key]);

  if (result) return <Result file={file} result={result} onPanel={onPanel} />;
  return (
    <form
      className="flex flex-col gap-5 p-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (ready) void submit.run();
      }}
    >
      <p className="text-body text-fg-muted">{file.story}</p>
      {file.questions.map((q) => (
        <Question
          key={q.key}
          q={q}
          value={choices[q.key]}
          onChange={(key) => setChoices((c) => ({ ...c, [q.key]: key }))}
        />
      ))}
      {submit.error ? (
        <p role="alert" className="text-body text-danger-text">
          {submit.error}
        </p>
      ) : null}
      <button
        type="submit"
        disabled={!ready || submit.busy}
        className="h-10 rounded-sm bg-brand px-4 text-body font-semibold text-on-brand hover:bg-brand-hover disabled:opacity-60"
      >
        {submit.busy ? "Checking…" : "Check my answers"}
      </button>
      {ready ? null : (
        <p className="text-caption text-fg-subtle">
          Answer all three. You get one go: the answers come back.
        </p>
      )}
    </form>
  );
}

function Question({
  q,
  value,
  onChange,
}: {
  q: CaseQuestionOut;
  value: string | undefined;
  onChange: (key: string) => void;
}) {
  return (
    <fieldset className="flex flex-col gap-1.5">
      <legend className="pb-1 text-body font-semibold text-fg">{q.prompt}</legend>
      {q.options.map((o) => (
        <label
          key={o.key}
          className="flex cursor-pointer items-start gap-2 rounded-sm border border-border px-2.5 py-2 text-label text-fg hover:bg-raised has-[:checked]:border-brand has-[:checked]:bg-brand-subtle"
        >
          <input
            type="radio"
            name={q.key}
            value={o.key}
            checked={value === o.key}
            onChange={() => onChange(o.key)}
            className="mt-0.5 shrink-0"
          />
          <span>{o.text}</span>
        </label>
      ))}
    </fieldset>
  );
}

function Result({
  file,
  result,
  onPanel,
}: {
  file: CaseFileOut;
  result: CaseResultOut;
  onPanel: (panel: string) => void;
}) {
  // Answers arrive in place of the form: move focus there, and screen readers follow.
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), []);
  const right = result.answers.filter((a) => a.correct).length;
  const text = (key: string, option: string) =>
    file.questions.find((q) => q.key === key)?.options.find((o) => o.key === option)?.text ?? "";
  return (
    <div className="flex flex-col gap-5 p-3">
      <div>
        <h2 ref={heading} tabIndex={-1} className="text-heading-md font-semibold text-fg outline-none">
          {right} of {result.answers.length} right
        </h2>
        <p className="font-mono text-mono text-fg-muted tabular-nums">Score {result.score} of 100</p>
      </div>
      <ul className="flex flex-col gap-4">
        {result.answers.map((a) => (
          <li key={a.key} className="flex flex-col gap-1">
            <h3 className="flex items-center gap-1.5 text-body font-semibold text-fg">
              {a.correct ? (
                <CircleCheck className="size-4 shrink-0 text-success-text" aria-hidden="true" />
              ) : (
                <CircleX className="size-4 shrink-0 text-danger-text" aria-hidden="true" />
              )}
              {SHORT[a.key]}:{" "}
              <span className={a.correct ? "text-success-text" : "text-danger-text"}>
                {a.correct ? "right" : "not quite"}
              </span>
            </h3>
            {a.correct ? null : <p className="text-label text-fg-muted">You said: {text(a.key, a.choice)}</p>}
            <p className="text-label font-medium text-fg">
              {a.correct ? null : "It was: "}
              {text(a.key, a.answer)}
            </p>
            <p className="text-label text-fg-muted">{a.explanation_md}</p>
          </li>
        ))}
      </ul>
      <section aria-labelledby="clues-title">
        <h3 id="clues-title" className="text-body font-semibold text-fg">
          Where the evidence showed it
        </h3>
        <ul className="mt-1.5 flex flex-col gap-1.5">
          {result.clues.map((c) => (
            <li key={c.note} className="text-label text-fg-muted">
              {c.panel === "commands" ? (
                <span className="font-medium text-fg">{PANEL_LABEL[c.panel]}</span>
              ) : (
                <button
                  type="button"
                  onClick={() => onPanel(c.panel)}
                  className="font-medium text-brand-text hover:underline"
                >
                  {PANEL_LABEL[c.panel]}
                </button>
              )}
              : {c.note}
            </li>
          ))}
        </ul>
      </section>
      <WriteUp slug={file.slug} result={result} />
      <div className="flex flex-col gap-2 border-t border-border pt-4">
        <p className="text-label text-fg-muted">Now try to fix one like it on a running system.</p>
        <div className="flex flex-wrap gap-2">
          <Link
            href={`/drills/${file.track_slug}/${file.slug}`}
            className="inline-flex h-9 items-center rounded-sm bg-brand px-3 text-label font-semibold text-on-brand hover:bg-brand-hover"
          >
            Play it live
          </Link>
          <Link
            href="/case-files"
            className="inline-flex h-9 items-center rounded-sm border border-border-input px-3 text-label font-medium text-fg hover:bg-raised"
          >
            More case files
          </Link>
        </div>
      </div>
    </div>
  );
}

/** Optional: explain it in your own words, and get an AI read within the plan's allowance. */
function WriteUp({ slug, result }: { slug: string; result: CaseResultOut }) {
  const [text, setText] = useState(result.write_up ?? "");
  const [note, setNote] = useState(result.review_note ?? null);
  const send = useAction(async () => {
    const out = await call(
      reviewCaseFile({ client: browserApi(), path: { slug }, body: { write_up: text } }),
    );
    setNote(out.note);
  });
  if (result.review === "off") return null;
  const here = `/sign-in?next=${encodeURIComponent(`/case-files/${slug}`)}`;
  if (result.review === "sign_in") {
    return (
      <p className="text-label text-fg-muted">
        <Link href={here} className="text-brand-text hover:underline">
          Sign in with GitHub
        </Link>{" "}
        to keep your score and get a short write-up reviewed.
      </p>
    );
  }
  return (
    <section aria-labelledby="write-up-title" className="flex flex-col gap-2">
      <h3 id="write-up-title" className="text-body font-semibold text-fg">
        Explain it in your own words (optional)
      </h3>
      {note ? (
        <>
          <p className="text-label whitespace-pre-wrap text-fg-muted">{text}</p>
          <p className="rounded-sm border border-border bg-raised p-2.5 text-label text-fg" role="status">
            {note}
          </p>
        </>
      ) : (
        <form
          className="flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void send.run();
          }}
        >
          <label htmlFor="case-write-up" className="sr-only">
            Your write-up
          </label>
          <textarea
            id="case-write-up"
            rows={4}
            maxLength={2000}
            value={text}
            onChange={(e) => setText(e.target.value)}
            className="rounded-sm border border-border-input bg-sunken px-2.5 py-2 text-label text-fg"
          />
          {send.error ? (
            <p role="alert" className="text-label text-danger-text">
              {send.error}
            </p>
          ) : null}
          <button
            type="submit"
            disabled={send.busy || text.trim().length < 20}
            className="h-9 self-start rounded-sm border border-border-input px-3 text-label font-medium text-fg hover:bg-raised disabled:opacity-60"
          >
            {send.busy ? "Reading it…" : "Get a review"}
          </button>
          <p className="text-caption text-fg-subtle">Counts as one of your plan&apos;s write-up reviews.</p>
        </form>
      )}
    </section>
  );
}
