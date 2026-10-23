import type { Meta, StoryObj } from "@storybook/react-vite";
import { useEffect, useState } from "react";
import { expect, userEvent, waitFor } from "storybook/test";
import { MetricChart } from "./metric-chart";
import { PanelFrame } from "./panel-frame";
import { VerifyCelebration } from "./verify-celebration";
import { WorkspaceLayout } from "./workspace-layout";

const meta = { title: "DevGrill/Workspace", parameters: { layout: "fullscreen" } } satisfies Meta;
export default meta;
type Story = StoryObj<typeof meta>;

const T0 = 1_760_383_800;
const ts = Array.from({ length: 31 }, (_, i) => T0 + i * 120);
const latency = ts.map((_, i) => (i < 15 ? 118 + Math.sin(i) * 6 : 4200 + Math.sin(i) * 200));

export const Chart: Story = {
  render: () => (
    <div className="max-w-xl p-6">
      <MetricChart
        title="p99 latency"
        summary="Rose from 118 ms to 4.2 s at 20:00; target 500 ms."
        timestamps={ts}
        series={[{ label: "p99", values: latency, color: 7 }]}
        format={(v) => (v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${Math.round(v)} ms`)}
        threshold={{ value: 500, label: "SLO" }}
        markers={[{ at: T0 + 14 * 120, label: "deploy" }]}
      />
    </div>
  ),
  play: async ({ canvas }) => {
    // The canvas is decorative to assistive tech; the figure carries a text summary.
    await expect(canvas.getByText(/Rose from 118 ms/)).toBeInTheDocument();
  },
};

function LiveChart() {
  const [points, setPoints] = useState(() => ts.map((t, i) => ({ t, v: 120 + (i % 5) * 4 })));
  useEffect(() => {
    const id = setInterval(() => {
      setPoints((prev) => {
        const last = prev[prev.length - 1]!;
        return [...prev.slice(1), { t: last.t + 120, v: 120 + Math.random() * 40 }];
      });
    }, 1000);
    return () => clearInterval(id);
  }, []);
  return (
    <div className="max-w-xl p-6">
      <MetricChart
        title="Requests per second (live, snaps without tweening)"
        summary="Live mock stream around 140 requests per second."
        timestamps={points.map((p) => p.t)}
        series={[{ label: "rps", values: points.map((p) => p.v), color: 1 }]}
      />
    </div>
  );
}

export const ChartLiveStream: Story = { render: () => <LiveChart />, tags: ["!test"] };

const pane = (title: string) => (
  <PanelFrame title={title}>
    <p className="p-3 text-body text-fg-muted">{title} content</p>
  </PanelFrame>
);

export const Layout: Story = {
  render: () => (
    <div className="h-[28rem] border border-border">
      <WorkspaceLayout
        storageId="story-workspace"
        primary={pane("Overview")}
        secondary={pane("Terminal")}
        side={pane("War room")}
      />
    </div>
  ),
  play: async ({ canvas }) => {
    // Window splitter pattern: separators are focusable and resize with the keyboard.
    await expect(canvas.getAllByRole("separator")).toHaveLength(2);
    // The team chat's splitter moves left and right; the terminal's moves up and down.
    for (const [name, key] of [
      [/work area and the team chat/, "{ArrowRight}{ArrowRight}"],
      [/tool panel and the terminal/, "{ArrowDown}{ArrowDown}"],
    ] as const) {
      const separator = canvas.getByRole("separator", { name });
      const before = Number(separator.getAttribute("aria-valuenow"));
      separator.focus();
      await userEvent.keyboard(key);
      await waitFor(() => expect(Number(separator.getAttribute("aria-valuenow"))).toBeGreaterThan(before));
    }
  },
};

export const Celebration: Story = {
  render: () => (
    <div className="max-w-4xl p-6">
      <VerifyCelebration
        title="Your fix works"
        delta={52}
        rating={1392}
        track="Caching"
        masteryBefore={36}
        masteryAfter={45}
      />
    </div>
  ),
  play: async ({ canvas }) => {
    await expect(canvas.getByRole("heading", { name: "Your fix works" })).toBeVisible();
    await expect(canvas.getByText("Up 52, now 1392")).toBeInTheDocument();
  },
};

export const CelebrationReducedMotion: Story = { ...Celebration, globals: { motion: "reduce" } };
export const CelebrationDark: Story = { ...Celebration, globals: { theme: "dark" } };
