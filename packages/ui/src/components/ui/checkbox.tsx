// Source: shadcn/ui registry (base-nova) "checkbox", adapted to DevGrill tokens.
"use client";

import { Checkbox as CheckboxPrimitive } from "@base-ui/react/checkbox";
import { cn } from "@devgrill/ui/lib/utils";
import { CheckIcon } from "lucide-react";

function Checkbox({ className, ...props }: CheckboxPrimitive.Root.Props) {
  return (
    <CheckboxPrimitive.Root
      data-slot="checkbox"
      className={cn(
        "peer relative flex size-4 shrink-0 items-center justify-center rounded-[4px] border border-border-input transition-colors outline-none group-has-disabled/field:opacity-50 group-has-[:focus-visible]/field-label:ring-0 group-has-[:focus-visible]/field-label:not-data-checked:border-border-input after:absolute after:-inset-x-3 after:-inset-y-2 focus-visible:border-focus-ring focus-visible:ring-3 focus-visible:ring-focus-ring/50 disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-danger-text aria-invalid:ring-3 aria-invalid:ring-danger-text/20 aria-invalid:aria-checked:border-brand data-checked:border-brand data-checked:bg-brand data-checked:text-on-brand group-has-[:focus-visible]/field-label:data-checked:border-brand dark:bg-border-input/30 dark:aria-invalid:border-danger-text/50 dark:aria-invalid:ring-danger-text/40 dark:data-checked:bg-brand",
        className,
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator
        data-slot="checkbox-indicator"
        className="grid place-content-center text-current transition-none [&>svg]:size-3.5"
      >
        <CheckIcon />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  );
}

export { Checkbox };
