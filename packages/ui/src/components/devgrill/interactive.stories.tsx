import type { Meta, StoryObj } from "@storybook/react-vite";
import { Code2, Database, Gauge, ScrollText } from "lucide-react";
import { useState } from "react";
import { expect, fn, userEvent, waitFor, within } from "storybook/test";
import { ApproachList, type Approach } from "./approach-list";
import { CommandPalette } from "./command-palette";
import { ThemeSwitch } from "./theme-controls";
import { ToolRail, type Tool } from "./tool-rail";

const meta = { title: "DevGrill/Interactive" } satisfies Meta;
export default meta;
type Story = StoryObj<typeof meta>;

const TOOLS: Tool[] = [
  { id: "overview", label: "Overview", icon: Gauge, badge: 2 },
  { id: "logs", label: "Logs", icon: ScrollText },
  { id: "database", label: "Database", icon: Database },
  { id: "code", label: "Code", icon: Code2, disabled: true },
];

function RailDemo() {
  const [tool, setTool] = useState("overview");
  return (
    <div className="flex w-56 flex-col gap-2 rounded-md border border-border bg-surface">
      <ToolRail tools={TOOLS} value={tool} onValueChange={setTool} panelId="panel" />
      <div
        id="panel"
        role="tabpanel"
        aria-labelledby={`tool-${tool}`}
        className="px-3 pb-3 text-label text-fg-muted"
      >
        Showing {tool}
      </div>
    </div>
  );
}

export const ToolRailKeyboard: Story = {
  render: () => <RailDemo />,
  play: async ({ canvas }) => {
    const overview = canvas.getByRole("tab", { name: /Overview/ });
    overview.focus();
    await userEvent.keyboard("{ArrowDown}");
    await expect(canvas.getByRole("tab", { name: "Logs" })).toHaveAttribute("aria-selected", "true");
    await expect(canvas.getByRole("tab", { name: "Logs" })).toHaveFocus();
    // Disabled tools are skipped; End jumps to the last enabled tool.
    await userEvent.keyboard("{End}");
    await expect(canvas.getByRole("tab", { name: "Database" })).toHaveAttribute("aria-selected", "true");
    await userEvent.keyboard("{ArrowDown}");
    await expect(canvas.getByRole("tab", { name: /Overview/ })).toHaveAttribute("aria-selected", "true");
  },
};

const APPROACHES: Approach[] = [
  { id: "coalesce", name: "Request coalescing", share: 38, outcome: "full", yours: true },
  { id: "jitter", name: "TTL jitter only", share: 9, outcome: "partial" },
  { id: "scale", name: "Scale up Postgres", share: 2, outcome: "fails" },
];

function ApproachDemo() {
  const [value, setValue] = useState("coalesce");
  return (
    <div className="max-w-sm">
      <ApproachList
        approaches={APPROACHES}
        value={value}
        onValueChange={setValue}
        label="Other ways to fix it"
      />
    </div>
  );
}

export const ApproachesKeyboard: Story = {
  render: () => <ApproachDemo />,
  play: async ({ canvas }) => {
    const group = canvas.getByRole("radiogroup", { name: "Other ways to fix it" });
    const first = within(group).getAllByRole("radio")[0]!;
    first.focus();
    await userEvent.keyboard("{ArrowDown}");
    await waitFor(() =>
      expect(within(group).getAllByRole("radio")[1]).toHaveAttribute("aria-checked", "true"),
    );
  },
};

export const ApproachesDark: Story = { render: () => <ApproachDemo />, globals: { theme: "dark" } };

const onSelect = fn();

function PaletteDemo() {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex flex-col items-start gap-2">
      <p className="text-body text-fg-muted">Press Ctrl+K (⌘K on a Mac) or use the button.</p>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="h-9 rounded-sm border border-border-input px-3 text-label text-fg"
      >
        Open command palette
      </button>
      <CommandPalette
        open={open}
        onOpenChange={setOpen}
        commands={[
          { id: "logs", group: "Panels", label: "Open Logs", icon: ScrollText, shortcut: "2", onSelect },
          { id: "db", group: "Panels", label: "Open Database", icon: Database, shortcut: "3", onSelect },
          {
            id: "verify",
            group: "This drill",
            label: "Check my fix",
            shortcut: "mod+shift+v",
            keywords: ["test", "verify"],
            onSelect,
          },
        ]}
      />
    </div>
  );
}

export const CommandPaletteKeyboard: Story = {
  render: () => <PaletteDemo />,
  play: async ({ canvas, canvasElement }) => {
    await userEvent.click(canvas.getByRole("button", { name: "Open command palette" }));
    const body = within(canvasElement.ownerDocument.body);
    const input = await body.findByRole("combobox");
    await expect(input).toHaveFocus();
    await userEvent.type(input, "verify");
    await expect(body.getByRole("option", { name: /Check my fix/ })).toBeVisible();
    await userEvent.keyboard("{Enter}");
    await expect(onSelect).toHaveBeenCalledOnce();
    await waitFor(() => expect(body.queryByRole("combobox")).toBeNull());
  },
};

export const ThemeSwitchStory: Story = {
  name: "Theme switch",
  render: () => <ThemeSwitch />,
  play: async ({ canvas }) => {
    const group = canvas.getByRole("group", { name: "Theme" });
    await expect(within(group).getAllByRole("button")).toHaveLength(3);
    await userEvent.click(within(group).getByRole("button", { name: "Dark" }));
    await expect(within(group).getByRole("button", { name: "Dark" })).toHaveAttribute("aria-pressed", "true");
  },
};
