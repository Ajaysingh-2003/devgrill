// Source: shadcn/ui registry (base-nova) "switch", adapted to DevGrill tokens.
"use client";

import { Switch as SwitchPrimitive } from "@base-ui/react/switch";
import { cn } from "@devgrill/ui/lib/utils";

function Switch({
  className,
  size = "default",
  ...props
}: SwitchPrimitive.Root.Props & {
  size?: "sm" | "default";
}) {
  return (
    <SwitchPrimitive.Root
      data-slot="switch"
      data-size={size}
      className={cn(
        "peer group/switch relative inline-flex shrink-0 items-center rounded-full border border-transparent transition-colors duration-(--duration-fast) ease-(--ease-standard) outline-none group-has-[:focus-visible]/field-label:border-transparent group-has-[:focus-visible]/field-label:ring-0 after:absolute after:-inset-x-3 after:-inset-y-2 focus-visible:border-focus-ring focus-visible:ring-3 focus-visible:ring-focus-ring/50 aria-invalid:border-danger-text aria-invalid:ring-3 aria-invalid:ring-danger-text/20 data-checked:bg-brand data-disabled:cursor-not-allowed data-disabled:opacity-50 data-unchecked:bg-border-input data-[size=default]:h-[18.4px] data-[size=default]:w-[32px] data-[size=sm]:h-[14px] data-[size=sm]:w-[24px] dark:aria-invalid:border-danger-text/50 dark:aria-invalid:ring-danger-text/40 dark:data-unchecked:bg-border-input/80",
        className,
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb
        data-slot="switch-thumb"
        className="pointer-events-none block rounded-full bg-surface ring-0 transition-transform duration-(--duration-fast) ease-(--ease-standard) group-data-[size=default]/switch:size-4 group-data-[size=sm]/switch:size-3 group-data-[size=default]/switch:data-checked:translate-x-[calc(100%-2px)] group-data-[size=sm]/switch:data-checked:translate-x-[calc(100%-2px)] group-data-[size=default]/switch:data-unchecked:translate-x-0 group-data-[size=sm]/switch:data-unchecked:translate-x-0 dark:data-checked:bg-on-brand dark:data-unchecked:bg-fg"
      />
    </SwitchPrimitive.Root>
  );
}

export { Switch };
