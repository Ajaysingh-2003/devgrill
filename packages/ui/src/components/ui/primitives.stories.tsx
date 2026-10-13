import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, userEvent, within } from "storybook/test";
import { Badge } from "./badge";
import { Button } from "./button";
import { Checkbox } from "./checkbox";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "./dialog";
import { Input } from "./input";
import { Kbd } from "./kbd";
import { Label } from "./label";
import { Progress } from "./progress";
import { Switch } from "./switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./tabs";
import { Textarea } from "./textarea";

const meta = { title: "Primitives/Overview" } satisfies Meta;
export default meta;
type Story = StoryObj<typeof meta>;

function Primitives() {
  return (
    <div className="flex max-w-2xl flex-col gap-6">
      <div className="flex flex-wrap items-center gap-2">
        <Button>Start the incident</Button>
        <Button variant="outline">Roll back</Button>
        <Button variant="secondary">Request a hint</Button>
        <Button variant="ghost">Cancel</Button>
        <Button variant="destructive">Abandon incident</Button>
        <Button variant="link">Read the primer</Button>
        <Button disabled>Verifying…</Button>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Badge>Published</Badge>
        <Badge variant="secondary">Draft</Badge>
        <Badge variant="outline">v3</Badge>
        <Kbd>Ctrl</Kbd>
        <Kbd>K</Kbd>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="handle">Handle</Label>
          <Input id="handle" placeholder="ajay" />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="bad">Invalid field</Label>
          <Input id="bad" aria-invalid defaultValue="no spaces allowed" aria-describedby="bad-help" />
          <p id="bad-help" className="text-label text-danger-text">
            Handles can’t contain spaces.
          </p>
        </div>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="update">Status update</Label>
        <Textarea id="update" placeholder="What you know, what you're doing next" />
      </div>
      <div className="flex flex-wrap items-center gap-6">
        <div className="flex items-center gap-2">
          <Checkbox id="freeze" defaultChecked />
          <Label htmlFor="freeze">Use a streak freeze</Label>
        </div>
        <div className="flex items-center gap-2">
          <Switch id="pro" />
          <Label htmlFor="pro">Pro mode</Label>
        </div>
      </div>
      <Progress value={45} aria-label="Caching mastery" />
      <Tabs defaultValue="war-room">
        <TabsList>
          <TabsTrigger value="war-room">War room</TabsTrigger>
          <TabsTrigger value="timeline">Timeline</TabsTrigger>
        </TabsList>
        <TabsContent value="war-room" className="text-body text-fg-muted">
          Messages from your teammates.
        </TabsContent>
        <TabsContent value="timeline" className="text-body text-fg-muted">
          Alerts and actions in order.
        </TabsContent>
      </Tabs>
      <Dialog>
        <DialogTrigger render={<Button variant="outline">Abandon incident…</Button>} />
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Abandon this incident?</DialogTitle>
            <DialogDescription>
              Your sandbox stops and this attempt won’t count toward your rating.
            </DialogDescription>
          </DialogHeader>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export const Light: Story = {
  render: () => <Primitives />,
  play: async ({ canvas, canvasElement }) => {
    await userEvent.click(canvas.getByRole("tab", { name: "Timeline" }));
    await expect(canvas.getByText("Alerts and actions in order.")).toBeVisible();
    await userEvent.click(canvas.getByRole("button", { name: "Abandon incident…" }));
    const dialog = await within(canvasElement.ownerDocument.body).findByRole("dialog");
    await expect(within(dialog).getByText("Abandon this incident?")).toBeVisible();
    await userEvent.keyboard("{Escape}");
  },
};

export const Dark: Story = { render: () => <Primitives />, globals: { theme: "dark" } };
