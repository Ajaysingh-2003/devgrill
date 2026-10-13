import { Toaster } from "@devgrill/ui/components/ui/sonner";
import { MotionPreferences } from "@devgrill/ui/theme/motion";

/** Incident routes (workspace, debrief, postmortem): animation preferences and toasts. */
export default function IncidentLayout({ children }: LayoutProps<"/">) {
  return (
    <MotionPreferences>
      {children}
      <Toaster position="bottom-right" />
    </MotionPreferences>
  );
}
