import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { Suspense } from "react";
import { pauseEmails } from "@devgrill/api-client";
import { api } from "@/lib/api";

export const metadata: Metadata = { title: "Pause emails", robots: { index: false } };

async function pause(formData: FormData) {
  "use server";
  const token = String(formData.get("token") ?? "");
  const { response } = await pauseEmails({ client: await api(), query: { token } });
  redirect(`/emails/pause?done=${response?.ok ? "1" : "0"}`);
}

/**
 * The pause link in every daily email. A button, not an automatic pause on opening: link
 * scanners open links too, and shouldn't pause anyone's email.
 */
async function Pause({ searchParams }: { searchParams: PageProps<"/emails/pause">["searchParams"] }) {
  const { token, done } = await searchParams;
  return (
    <>
      {done === "1" ? (
        <>
          <h1 className="text-heading-lg font-semibold tracking-tight text-fg">Emails paused</h1>
          <p className="text-body-lg text-fg-muted">
            You won’t get the daily email any more. Turn it back on any time in Settings.
          </p>
          <Link href="/settings" className="text-body font-medium text-brand-text hover:underline">
            Open Settings
          </Link>
        </>
      ) : done === "0" || typeof token !== "string" || !token ? (
        <>
          <h1 className="text-heading-lg font-semibold tracking-tight text-fg">This link didn’t work</h1>
          <p className="text-body-lg text-fg-muted">
            It may be cut short. You can turn the daily email off in Settings instead.
          </p>
          <Link href="/settings" className="text-body font-medium text-brand-text hover:underline">
            Open Settings
          </Link>
        </>
      ) : (
        <form action={pause} className="flex flex-col gap-5">
          <h1 className="text-heading-lg font-semibold tracking-tight text-fg">Pause the daily email?</h1>
          <p className="text-body-lg text-fg-muted">
            No more daily emails until you turn them back on in Settings. Your streak isn’t affected.
          </p>
          <input type="hidden" name="token" value={token} />
          <button
            type="submit"
            className="inline-flex h-10 w-fit items-center rounded-sm bg-brand px-4 text-body font-semibold text-on-brand hover:bg-brand-hover"
          >
            Pause emails
          </button>
        </form>
      )}
    </>
  );
}

export default function PauseEmailsPage({ searchParams }: PageProps<"/emails/pause">) {
  return (
    <div className="mx-auto flex max-w-xl flex-col gap-5 px-4 py-16 sm:px-6">
      <Suspense fallback={null}>
        <Pause searchParams={searchParams} />
      </Suspense>
    </div>
  );
}
