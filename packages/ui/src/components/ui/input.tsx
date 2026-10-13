// Source: shadcn/ui registry (base-nova) "input", adapted to DevGrill tokens.
import * as React from "react";
import { Input as InputPrimitive } from "@base-ui/react/input";
import { cn } from "@devgrill/ui/lib/utils";

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <InputPrimitive
      type={type}
      data-slot="input"
      className={cn(
        "h-8 w-full min-w-0 rounded-lg border border-border-input bg-transparent px-2.5 py-1 text-base transition-colors outline-none file:inline-flex file:h-6 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-fg placeholder:text-fg-muted focus-visible:border-focus-ring focus-visible:ring-3 focus-visible:ring-focus-ring/50 disabled:pointer-events-none disabled:cursor-not-allowed disabled:bg-border-input/50 disabled:opacity-50 aria-invalid:border-danger-text aria-invalid:ring-3 aria-invalid:ring-danger-text/20 md:text-sm dark:bg-border-input/30 dark:disabled:bg-border-input/80 dark:aria-invalid:border-danger-text/50 dark:aria-invalid:ring-danger-text/40",
        className,
      )}
      {...props}
    />
  );
}

export { Input };
