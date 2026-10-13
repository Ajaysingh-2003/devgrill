// Source: shadcn/ui registry (base-nova) "textarea", adapted to DevGrill tokens.
import * as React from "react";
import { cn } from "@devgrill/ui/lib/utils";

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "flex field-sizing-content min-h-16 w-full rounded-lg border border-border-input bg-transparent px-2.5 py-2 text-base transition-colors outline-none placeholder:text-fg-muted focus-visible:border-focus-ring focus-visible:ring-3 focus-visible:ring-focus-ring/50 disabled:cursor-not-allowed disabled:bg-border-input/50 disabled:opacity-50 aria-invalid:border-danger-text aria-invalid:ring-3 aria-invalid:ring-danger-text/20 md:text-sm dark:bg-border-input/30 dark:disabled:bg-border-input/80 dark:aria-invalid:border-danger-text/50 dark:aria-invalid:ring-danger-text/40",
        className,
      )}
      {...props}
    />
  );
}

export { Textarea };
