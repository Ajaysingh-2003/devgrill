import type { Metadata } from "next";
import { Suspense } from "react";
import { getMe } from "@devgrill/api-client";
import { MotionSetting, ThemeSwitch } from "@devgrill/ui/components/devgrill/theme-controls";
import { PageHeader } from "@/components/page-header";
import { PageSkeleton } from "@/components/page-skeleton";
import { api, unwrap } from "@/lib/api";
import { requireSession } from "@/lib/auth";
import { ProModeSwitch } from "./pro-mode-switch";

export const metadata: Metadata = { title: "Settings" };

async function Preferences() {
  await requireSession("/settings");
  const me = await unwrap(getMe({ client: await api() }));
  return (
    <>
      <section
        aria-labelledby="appearance"
        className="flex flex-col gap-3 rounded-md border border-border bg-surface p-5"
      >
        <h2 id="appearance" className="text-body font-semibold text-fg">
          Theme
        </h2>
        <ThemeSwitch className="self-start" />
      </section>
      <section className="rounded-md border border-border bg-surface p-5">
        <MotionSetting />
      </section>
      <section
        aria-labelledby="pro-mode"
        className="flex flex-col gap-3 rounded-md border border-border bg-surface p-5"
      >
        <div className="flex flex-col gap-1">
          <h2 id="pro-mode" className="text-body font-semibold text-fg">
            Pro mode
          </h2>
          <p className="text-body text-fg-muted">
            Hides streaks and leagues for people who just want the drills.
          </p>
        </div>
        <ProModeSwitch initial={me.prefs.pro_mode ?? false} />
      </section>
    </>
  );
}

/** T2 app page: settings. Saved to your profile, so they follow you to other devices. */
export default function SettingsPage() {
  return (
    <div className="flex max-w-2xl flex-col gap-8">
      <PageHeader title="Settings" description="Saved to your profile, so they follow you to every device." />
      <Suspense fallback={<PageSkeleton label="Loading settings" />}>
        <Preferences />
      </Suspense>
    </div>
  );
}
