import { adminAiCosts, adminApproachCandidates } from "@devgrill/api-client";
import { api } from "@/lib/api";
import { CandidateActions } from "./candidate-actions";

const SMALL = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 4,
});
const LARGE = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const usd = (n: number) => (n < 1 ? SMALL : LARGE).format(n);

/** Model spend from llm_calls: today against the budget, and the last 7 days by feature. */
export async function AiSpend() {
  const { data } = await adminAiCosts({ client: await api() });
  if (!data) return null;
  const share = data.budget_usd ? data.spent_today_usd / data.budget_usd : 0;
  return (
    <div className="flex flex-col gap-3">
      <dl className="grid gap-px overflow-hidden rounded-md border border-border bg-border sm:grid-cols-3">
        {(
          [
            ["Spent today (IST)", usd(data.spent_today_usd), `of ${usd(data.budget_usd)} budget`],
            ["Budget used", `${Math.round(share * 100)}%`, share >= 0.8 ? "alarm at 80%" : "under the alarm"],
            [
              "Per attempt, 7 days",
              data.per_attempt_usd == null ? "–" : usd(data.per_attempt_usd),
              "target ≤ $0.03",
            ],
          ] as const
        ).map(([k, v, note]) => (
          <div key={k} className="flex flex-col gap-0.5 bg-surface px-4 py-3">
            <dt className="text-label text-fg-muted">{k}</dt>
            <dd className="font-mono text-stat font-semibold text-fg tabular-nums">{v}</dd>
            <dd className="text-caption text-fg-subtle">{note}</dd>
          </div>
        ))}
      </dl>
      <div className="overflow-x-auto rounded-md border border-border bg-surface">
        <table className="w-full min-w-[40rem] text-left text-body">
          <caption className="sr-only">Model calls in the last 7 days, by feature</caption>
          <thead className="border-b border-border text-caption text-fg-subtle">
            <tr>
              {["Feature", "Calls", "Errors", "Cost", "Tokens in / out", "p95 latency"].map((h) => (
                <th key={h} scope="col" className="px-3 py-2 font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="font-mono text-mono tabular-nums">
            {data.features.length ? (
              data.features.map((f) => (
                <tr key={f.feature} className="border-b border-border last:border-b-0">
                  <th scope="row" className="px-3 py-2 font-medium text-fg">
                    {f.feature}
                  </th>
                  <td className="px-3 py-2">{f.calls}</td>
                  <td className="px-3 py-2">{f.errors}</td>
                  <td className="px-3 py-2">{usd(f.cost_usd)}</td>
                  <td className="px-3 py-2 text-fg-muted">
                    {f.input_tokens} / {f.output_tokens}
                  </td>
                  <td className="px-3 py-2 text-fg-muted">
                    {f.p95_latency_ms == null ? "–" : `${f.p95_latency_ms} ms`}
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={6} className="px-3 py-3 font-sans text-fg-muted">
                  No model calls in the last 7 days.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** Fixes the classifier didn't recognise, grouped by similarity, for an author to write up. */
export async function ApproachQueue() {
  const { data } = await adminApproachCandidates({ client: await api() });
  if (!data) return null;
  if (!data.length) return <p className="text-body text-fg-muted">No unrecognised fixes waiting.</p>;
  return (
    <ul className="flex flex-col gap-3">
      {data.map((g) => (
        <li
          key={g.candidates[0]!.id}
          className="flex flex-col gap-2 rounded-md border border-border bg-surface p-3"
        >
          <p className="text-label text-fg-muted">
            <span className="font-mono text-fg">{g.scenario_slug}</span>, {g.candidates.length} similar{" "}
            {g.candidates.length === 1 ? "fix" : "fixes"}
          </p>
          <ul className="flex flex-col gap-2">
            {g.candidates.map((c) => (
              <li key={c.id} className="flex flex-wrap items-start justify-between gap-2">
                <span id={`candidate-${c.id}`} className="max-w-3xl text-body text-fg">
                  {c.summary}
                </span>
                <CandidateActions id={c.id} describedBy={`candidate-${c.id}`} />
              </li>
            ))}
          </ul>
        </li>
      ))}
    </ul>
  );
}
