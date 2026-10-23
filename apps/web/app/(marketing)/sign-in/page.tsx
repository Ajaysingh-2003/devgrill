import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { Suspense } from "react";
import { getSession } from "@/lib/auth";
import { safeNext } from "@/lib/safe-next";
import { SignInButton } from "./sign-in-button";

export const metadata: Metadata = { title: "Sign in" };

async function SignInForm({ searchParams }: { searchParams: PageProps<"/sign-in">["searchParams"] }) {
  const params = await searchParams;
  const next = safeNext(params.next);
  if (await getSession()) redirect(next);
  const failed = params.error !== undefined;
  return (
    <>
      {failed ? (
        <p role="alert" className="rounded-sm bg-danger-subtle px-3 py-2 text-body text-danger-text">
          GitHub sign-in didn’t complete. Try again; if it keeps failing, check that you approved access on
          GitHub.
        </p>
      ) : null}
      <SignInButton next={next} />
    </>
  );
}

/** Sign in with GitHub (the only provider for now; see ADR 011). */
export default function SignInPage(props: PageProps<"/sign-in">) {
  return (
    <div className="mx-auto flex max-w-sm flex-col gap-6 px-4 py-20">
      <div className="flex flex-col gap-2">
        <h1 className="text-heading-lg font-semibold tracking-tight text-fg">
          Sign in to save your progress
        </h1>
        <p className="text-body text-fg-muted">Ratings, streaks and write-ups are kept on your account.</p>
      </div>
      <Suspense fallback={<div className="h-11 rounded-sm bg-raised" />}>
        <SignInForm searchParams={props.searchParams} />
      </Suspense>
      <p className="text-label text-fg-subtle">
        Just looking?{" "}
        <Link href="/drills" className="font-medium text-brand-text hover:underline">
          Browse the drills without an account
        </Link>
      </p>
    </div>
  );
}
