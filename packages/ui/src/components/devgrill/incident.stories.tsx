import type { Meta, StoryObj } from "@storybook/react-vite";
import { CircleSlash, Inbox } from "lucide-react";
import { expect } from "storybook/test";
import { BootSequence } from "./boot-sequence";
import { EmptyState } from "./empty-state";
import { IncidentTimeline, type TimelineEvent } from "./incident-timeline";
import { LogView, type LogLine } from "./log-view";
import { PanelFrame } from "./panel-frame";
import { ProbeTable, type Probe } from "./probe-table";

const meta = { title: "DevGrill/Incident" } satisfies Meta;
export default meta;
type Story = StoryObj<typeof meta>;

const probes: Probe[] = [
  {
    key: "a",
    name: "Sale replay at 10x",
    how: "Replays the 20:00 traffic shape",
    observed: "p99 180 ms",
    target: "< 500 ms",
    outcome: "pass",
  },
  {
    key: "b",
    name: "Hot key expires mid-load",
    how: "Deletes product:1042 under load",
    observed: "3,900 queries/s",
    target: "< 50/s",
    outcome: "fail",
  },
  {
    key: "c",
    name: "Cold cache",
    how: "Flushes Redis at peak",
    observed: "41 s",
    target: "< 30 s",
    outcome: "partial",
  },
  {
    key: "d",
    name: "Hidden correctness tests",
    how: "API contract and edge cases",
    target: "all pass",
    outcome: "running",
  },
  { key: "e", name: "Resource budget", how: "No bigger database", target: "no scale-up", outcome: "queued" },
];

export const Probes: Story = {
  render: () => <ProbeTable probes={probes} caption="Checks" />,
  play: async ({ canvas }) => {
    await expect(canvas.getByRole("table", { name: "Checks" })).toBeVisible();
    for (const label of ["Pass", "Fail", "Partial", "Running", "Queued"]) {
      await expect(canvas.getByText(label)).toBeVisible();
    }
  },
};

export const ProbesDark: Story = { ...Probes, globals: { theme: "dark" } };

const events: TimelineEvent[] = [
  { id: "1", at: "00:00", kind: "alert", text: "SEV1 page: product-api p99 latency 4.2 s" },
  {
    id: "2",
    at: "00:20",
    kind: "beat",
    actor: "Priya (product)",
    text: "Product pages are dying. What's happening?",
  },
  { id: "3", at: "04:02", kind: "action", text: "Ran pg_stat_statements" },
  { id: "4", at: "06:10", kind: "rollback", text: "Rolled back product-api to 7bd21e0" },
  { id: "5", at: "07:00", kind: "hint", text: "Compare the keys the app asks for with the keys in Redis" },
  { id: "6", at: "09:30", kind: "deploy", text: "Deployed fix/inc-4021" },
];

export const Timeline: Story = {
  render: () => (
    <div className="max-w-md rounded-md border border-border bg-surface">
      <IncidentTimeline events={events} />
    </div>
  ),
};

const lines: LogLine[] = [
  { id: "1", ts: "20:00:00", level: "info", service: "load-gen", message: "sale profile engaged (10x)" },
  {
    id: "2",
    ts: "20:00:01",
    level: "warn",
    service: "product-api",
    message: "cache MISS key=v2:product:1042",
  },
  {
    id: "3",
    ts: "20:00:02",
    level: "error",
    service: "product-api",
    message: "db pool exhausted (100/100) waiting=812",
  },
  { id: "4", ts: "20:00:04", level: "debug", service: "worker", message: "orders queue depth=12" },
];

export const Logs: Story = {
  render: () => (
    <div className="h-64 max-w-2xl overflow-hidden rounded-md border border-border">
      <PanelFrame title="Logs" meta="service:product-api">
        <LogView lines={lines} />
      </PanelFrame>
    </div>
  ),
  play: async ({ canvas }) => {
    await expect(canvas.getByRole("heading", { name: "Logs" })).toBeVisible();
    await expect(canvas.getByRole("log", { name: "Logs" })).toBeVisible();
  },
};

export const Boot: Story = {
  render: () => (
    <div className="max-w-md">
      <BootSequence
        title="Starting your incident"
        steps={[
          { id: "1", label: "Allocating your sandbox", state: "done" },
          { id: "2", label: "Starting ShopKart", detail: "api, worker, postgres and redis", state: "done" },
          { id: "3", label: "Shipping the 19:58 deploy", state: "active" },
          { id: "4", label: "Starting sale traffic", state: "pending" },
        ]}
      />
    </div>
  ),
};

export const BootFailed: Story = {
  render: () => (
    <div className="max-w-md">
      <BootSequence
        title="Starting your incident"
        steps={[
          { id: "1", label: "Allocating your sandbox", state: "done" },
          {
            id: "2",
            label: "Starting ShopKart",
            detail: "postgres did not become healthy in 60 s",
            state: "failed",
          },
          { id: "3", label: "Starting sale traffic", state: "pending" },
        ]}
      />
    </div>
  ),
};

export const Empty: Story = {
  render: () => (
    <div className="flex flex-col gap-6">
      <div className="max-w-sm rounded-md border border-border bg-surface">
        <EmptyState icon={Inbox} title="No alerts firing yet" compact>
          Alerts appear here when an SLO is breached.
        </EmptyState>
      </div>
      <div className="rounded-md border border-border bg-surface">
        <EmptyState
          icon={CircleSlash}
          title="No postmortems yet"
          action={
            <button
              type="button"
              className="h-9 rounded-sm bg-brand px-4 text-label font-semibold text-on-brand"
            >
              Start today’s incident
            </button>
          }
        >
          Your first postmortem will live here.
        </EmptyState>
      </div>
    </div>
  ),
};
