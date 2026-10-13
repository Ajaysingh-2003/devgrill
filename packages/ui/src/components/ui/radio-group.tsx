// Source: shadcn/ui registry (base-nova) "radio-group", adapted to DevGrill tokens.
"use client";

import { Radio as RadioPrimitive } from "@base-ui/react/radio";
import { RadioGroup as RadioGroupPrimitive } from "@base-ui/react/radio-group";
import { cn } from "@devgrill/ui/lib/utils";

function RadioGroup({ className, ...props }: RadioGroupPrimitive.Props) {
  return (
    <RadioGroupPrimitive data-slot="radio-group" className={cn("grid w-full gap-2", className)} {...props} />
  );
}

function RadioGroupItem({ className, ...props }: RadioPrimitive.Root.Props) {
  return (
    <RadioPrimitive.Root
      data-slot="radio-group-item"
      className={cn(
        "group/radio-group-item peer relative flex aspect-square size-4 shrink-0 rounded-full border border-border-input outline-none group-has-[:focus-visible]/field-label:ring-0 group-has-[:focus-visible]/field-label:not-data-checked:border-border-input after:absolute after:-inset-x-3 after:-inset-y-2 focus-visible:border-focus-ring focus-visible:ring-3 focus-visible:ring-focus-ring/50 disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-danger-text aria-invalid:ring-3 aria-invalid:ring-danger-text/20 aria-invalid:aria-checked:border-brand data-checked:border-brand data-checked:bg-brand data-checked:text-on-brand group-has-[:focus-visible]/field-label:data-checked:border-brand dark:bg-border-input/30 dark:aria-invalid:border-danger-text/50 dark:aria-invalid:ring-danger-text/40 dark:data-checked:bg-brand",
        className,
      )}
      {...props}
    >
      <RadioPrimitive.Indicator
        data-slot="radio-group-indicator"
        className="flex size-4 items-center justify-center"
      >
        <span className="absolute top-1/2 left-1/2 size-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-on-brand" />
      </RadioPrimitive.Indicator>
    </RadioPrimitive.Root>
  );
}

export { RadioGroup, RadioGroupItem };
