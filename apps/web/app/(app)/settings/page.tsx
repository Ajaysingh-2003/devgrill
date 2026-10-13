import type { Metadata } from "next";
import { MotionSetting, ThemeSwitch } from "@devgrill/ui/components/devgrill/theme-controls";
import { PageHeader } from "@/components/page-header";

export const metadata: Metadata = { title: "Settings" };

/** T2 app page: settings. Preferences are stored on this device in phase 1, on your profile from phase 2. */
export default function SettingsPage() {
  return (
    <div className="flex max-w-2xl flex-col gap-8">
      <PageHeader title="Settings" description="Appearance and accessibility apply on this device." />
      <section
        aria-labelledby="appearance"
        className="flex flex-col gap-3 rounded-md border border-border bg-surface p-5"
      >
        <h2 id="appearance" className="text-body font-semibold text-fg">
          Theme
        </h2>
        <ThemeSwitch />
      </section>
      <section className="rounded-md border border-border bg-surface p-5">
        <MotionSetting />
      </section>
      <section
        aria-labelledby="pro-mode"
        className="flex flex-col gap-2 rounded-md border border-border bg-surface p-5"
      >
        <h2 id="pro-mode" className="text-body font-semibold text-fg">
          Pro mode
        </h2>
        <p className="text-body text-fg-muted">
          Hides streaks and leagues for people who just want the drills. Arrives in phase 7.
        </p>
      </section>
    </div>
  );
}
