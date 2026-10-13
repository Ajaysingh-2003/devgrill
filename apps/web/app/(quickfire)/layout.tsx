import { fontArcade } from "../fonts";

/** Quick Fire (mobile-first, Arcade layer). Kept light: no motion library, no toasts. */
export default function QuickFireLayout({ children }: LayoutProps<"/">) {
  return <div className={fontArcade.variable}>{children}</div>;
}
