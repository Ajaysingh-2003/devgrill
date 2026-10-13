import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "Sign in" };

/** Sign-in shell. GitHub OAuth (Better Auth) is wired in phase 2. */
export default function SignInPage() {
  return (
    <div className="mx-auto flex max-w-sm flex-col gap-6 px-4 py-20">
      <div className="flex flex-col gap-2">
        <h1 className="text-heading-lg font-semibold tracking-tight text-fg">
          Sign in to save your progress
        </h1>
        <p className="text-body text-fg-muted">Ratings, streaks and postmortems are kept on your account.</p>
      </div>
      <button
        type="button"
        className="flex h-11 items-center justify-center gap-2.5 rounded-sm bg-fg text-body font-semibold text-fg-inverse hover:opacity-90"
      >
        <svg viewBox="0 0 16 16" aria-hidden="true" className="size-4 fill-current">
          <path d="M8 0C3.58 0 0 3.58 0 8a8 8 0 0 0 5.47 7.59c.4.07.55-.17.55-.38v-1.33c-2.23.48-2.7-1.07-2.7-1.07-.36-.92-.89-1.17-.89-1.17-.73-.5.06-.49.06-.49.8.06 1.23.83 1.23.83.72 1.23 1.87.87 2.33.67.07-.52.28-.87.5-1.07-1.78-.2-3.65-.89-3.65-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.6 7.6 0 0 1 4 0c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.28.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48v2.2c0 .21.15.46.55.38A8 8 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
        </svg>
        Continue with GitHub
      </button>
      <p className="text-label text-fg-subtle">
        Just looking?{" "}
        <Link href="/drills" className="font-medium text-brand-text hover:underline">
          Try a drill without an account
        </Link>
      </p>
    </div>
  );
}
