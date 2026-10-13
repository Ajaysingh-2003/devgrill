import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";
import { MasteryRing } from "./mastery-ring";
import { RatingDelta } from "./rating-delta";
import { SevBadge } from "./sev-badge";
import { StatusPill, type Status } from "./status-pill";
import { Streak } from "./streak";

const meta = {
  title: "DevGrill/Badges and indicators",
  parameters: { layout: "padded" },
} satisfies Meta;
export default meta;
type Story = StoryObj<typeof meta>;

const STATUSES: Status[] = [
  "firing",
  "degraded",
  "investigating",
  "mitigated",
  "resolved",
  "healthy",
  "unknown",
];

function AllIndicators() {
  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-2">
        <h2 className="text-label font-semibold text-fg-muted">Severity (glyph + label + colour)</h2>
        <div className="flex flex-wrap gap-3">
          {([1, 2, 3, 4] as const).map((s) => (
            <SevBadge key={s} sev={s} />
          ))}
        </div>
        <div className="flex flex-wrap gap-3">
          {([1, 2, 3, 4] as const).map((s) => (
            <SevBadge key={s} sev={s} showName size="md" />
          ))}
        </div>
      </section>
      <section className="flex flex-col gap-2">
        <h2 className="text-label font-semibold text-fg-muted">Status</h2>
        <div className="flex flex-wrap gap-2">
          {STATUSES.map((s) => (
            <StatusPill key={s} status={s} />
          ))}
        </div>
      </section>
      <section className="flex flex-col gap-2">
        <h2 className="text-label font-semibold text-fg-muted">Rating delta</h2>
        <div className="flex flex-wrap gap-3">
          <RatingDelta delta={52} rating={1392} track="Caching" />
          <RatingDelta delta={-14} rating={1288} track="Databases" />
          <RatingDelta delta={0} rating={1200} track="Networking" />
        </div>
      </section>
      <section className="flex flex-col gap-2">
        <h2 className="text-label font-semibold text-fg-muted">Mastery and streak</h2>
        <div className="flex flex-wrap items-center gap-4">
          <MasteryRing value={0} label="Networking" />
          <MasteryRing value={45} label="Caching" />
          <MasteryRing value={100} label="Concurrency" size={56} />
          <Streak days={12} />
          <Streak days={3} unit="week" />
          <Streak days={12} frozen />
        </div>
      </section>
    </div>
  );
}

export const Light: Story = {
  render: () => <AllIndicators />,
  play: async ({ canvas }) => {
    // Severity is never colour alone: the text label is present.
    // Two rows of four badges, each with a text label (never colour alone).
    await expect(canvas.getAllByText(/^SEV[1-4]/)).toHaveLength(8);
    await expect(canvas.getByText("Caching rating up 52, now 1392")).toBeInTheDocument();
    await expect(canvas.getByRole("img", { name: "Caching: 45% mastered" })).toBeVisible();
  },
};

export const Dark: Story = { render: () => <AllIndicators />, globals: { theme: "dark" } };
