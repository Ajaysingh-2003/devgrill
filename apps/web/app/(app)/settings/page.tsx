import type { Metadata } from "next";
import { Suspense } from "react";
import { getMe, myLeave } from "@devgrill/api-client";
import { MotionSetting, ThemeSwitch } from "@devgrill/ui/components/devgrill/theme-controls";
import { PageHeader } from "@/components/page-header";
import { PageSkeleton } from "@/components/page-skeleton";
import { api, unwrap } from "@/lib/api";
import { requireSession } from "@/lib/auth";
import { EmailSettings } from "./email-settings";
import { LeaveSettings } from "./leave-settings";
import { ProModeSwitch } from "./pro-mode-switch";
import { PublicProfileSwitch } from "./public-profile-switch";

export const metadata: Metadata = { title: "Settings" };

async function Preferences() {
  await requireSession("/settings");
  const client = await api();
  const [me, leave] = await Promise.all([unwrap(getMe({ client })), unwrap(myLeave({ client }))]);
  // The player's own calendar day (leave is booked in it).
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: me.prefs.timezone ?? "Asia/Kolkata" }).format(
    new Date(),
  );
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
            Hides streaks, celebrations and reminders for people who just want the drills. Your ratings stay.
          </p>
        </div>
        <ProModeSwitch initial={me.prefs.pro_mode ?? false} />
      </section>
      <section
        aria-labelledby="public-profile"
        className="flex flex-col gap-3 rounded-md border border-border bg-surface p-5"
      >
        <div className="flex flex-col gap-1">
          <h2 id="public-profile" className="text-body font-semibold text-fg">
            Public profile
          </h2>
          <p className="text-body text-fg-muted">
            Shows your name, ratings and drills solved. Your drill history, streak and plan always stay
            private.
          </p>
        </div>
        <PublicProfileSwitch initial={me.is_public} handle={me.handle} />
      </section>
      <section
        aria-labelledby="daily-email"
        className="flex flex-col gap-3 rounded-md border border-border bg-surface p-5"
      >
        <div className="flex flex-col gap-1">
          <h2 id="daily-email" className="text-body font-semibold text-fg">
            Daily email
          </h2>
          <p className="text-body text-fg-muted">
            Today’s drill and your streak, at most once a day and never between 22:00 and 08:00. Every email
            has a one-tap pause.
          </p>
        </div>
        <EmailSettings
          initialOn={me.prefs.email_digest ?? false}
          initialHour={me.prefs.digest_hour ?? 9}
          hasEmail={me.has_email ?? false}
        />
      </section>
      <section
        aria-labelledby="leave"
        className="flex flex-col gap-3 rounded-md border border-border bg-surface p-5"
      >
        <div className="flex flex-col gap-1">
          <h2 id="leave" className="text-body font-semibold text-fg">
            On-call leave
          </h2>
          <p className="text-body text-fg-muted">
            Days off don’t break your streak. Book them ahead, up to 90 days out. You also earn a streak
            freeze for every 7 days in a row you play (4 weeks on a weekly streak, 2 at most), and it covers a
            missed day by itself.
          </p>
        </div>
        <LeaveSettings initial={leave.days} today={today} />
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
