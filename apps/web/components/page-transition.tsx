import { ViewTransition, type ReactNode } from "react";

const DIRECTIONAL = { "nav-forward": "nav-forward", "nav-back": "nav-back", default: "none" };

/**
 * Route transition for the drills hierarchy (drills → track → briefing): forward goes deeper,
 * back returns. Links opt in with `transitionTypes`; untyped navigations swap instantly.
 * Wrap each page, not the layout: layouts persist, so enter/exit never fire there.
 * The CSS lives in globals.css and uses motion tokens, which drop to 0ms under reduced motion.
 */
export function PageTransition({ children }: { children: ReactNode }) {
  return (
    <ViewTransition enter={DIRECTIONAL} exit={DIRECTIONAL} default="none">
      {children}
    </ViewTransition>
  );
}
