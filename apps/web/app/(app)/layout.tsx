import { Suspense } from "react";
import { Toaster } from "@devgrill/ui/components/ui/sonner";
import { MotionPreferences } from "@devgrill/ui/theme/motion";
import { PrefsSync } from "@/components/prefs-sync";
import { QueryProvider } from "@/components/query-provider";
import { TopBar } from "@/components/top-bar";
import { TopBarShell } from "@/components/top-bar-shell";
import { getViewer } from "@/lib/viewer";
import { fontArcade } from "../fonts";

/** The account-aware top bar. Streams in; the static bar holds its place meanwhile. */
async function SignedInTopBar() {
  const viewer = await getViewer();
  return (
    <>
      <TopBar viewer={viewer} />
      {viewer ? <PrefsSync theme={viewer.prefs.theme} motion={viewer.prefs.motion} /> : null}
    </>
  );
}

/** T2 app shell: top bar + centred content column. */
export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <QueryProvider>
      <MotionPreferences>
        {/* The Arcade face is used by the streak counter in the top bar. */}
        <div className={`${fontArcade.variable} flex min-h-dvh flex-col`}>
          <Suspense fallback={<TopBarShell />}>
            <SignedInTopBar />
          </Suspense>
          <main id="main" className="mx-auto w-full max-w-[75rem] flex-1 px-4 py-8 sm:px-6 sm:py-10">
            {children}
          </main>
        </div>
        <Toaster position="bottom-right" />
      </MotionPreferences>
    </QueryProvider>
  );
}
