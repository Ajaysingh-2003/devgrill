import { Toaster } from "@devgrill/ui/components/ui/sonner";
import { MotionPreferences } from "@devgrill/ui/theme/motion";
import { TopBar } from "@/components/top-bar";
import { PROFILE } from "@/lib/mock";
import { fontArcade } from "../fonts";

/** T2 app shell: top bar + centred content column. */
export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <MotionPreferences>
      {/* The Arcade face is used by the streak counter in the top bar. */}
      <div className={`${fontArcade.variable} flex min-h-dvh flex-col`}>
        <TopBar streakDays={PROFILE.streakDays} />
        <main id="main" className="mx-auto w-full max-w-[75rem] flex-1 px-4 py-8 sm:px-6 sm:py-10">
          {children}
        </main>
      </div>
      <Toaster position="bottom-right" />
    </MotionPreferences>
  );
}
