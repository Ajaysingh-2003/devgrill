// Source: shadcn/ui registry (base-nova) "button", adapted to DevGrill tokens.
import { Button as ButtonPrimitive } from "@base-ui/react/button";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@devgrill/ui/lib/utils";

const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center rounded-lg border border-transparent bg-clip-padding text-sm font-medium whitespace-nowrap transition-[color,background-color,border-color,box-shadow,translate] duration-(--duration-fast) ease-(--ease-standard) outline-none select-none focus-visible:border-focus-ring focus-visible:ring-3 focus-visible:ring-focus-ring/50 active:not-aria-[haspopup]:translate-y-px disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-danger-text aria-invalid:ring-3 aria-invalid:ring-danger-text/20 dark:aria-invalid:border-danger-text/50 dark:aria-invalid:ring-danger-text/40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default: "bg-brand text-on-brand hover:bg-brand/80",
        outline:
          "border-border bg-surface hover:bg-raised hover:text-fg aria-expanded:bg-raised aria-expanded:text-fg dark:border-border-input dark:bg-border-input/30 dark:hover:bg-border-input/50",
        secondary:
          "bg-raised text-fg hover:bg-[color-mix(in_oklch,var(--raised),var(--text)_5%)] aria-expanded:bg-raised aria-expanded:text-fg",
        ghost:
          "hover:bg-raised hover:text-fg aria-expanded:bg-raised aria-expanded:text-fg dark:hover:bg-raised/50",
        destructive:
          "bg-danger-text/10 text-danger-text hover:bg-danger-text/20 focus-visible:border-danger-text/40 focus-visible:ring-danger-text/20 dark:bg-danger-text/20 dark:hover:bg-danger-text/30 dark:focus-visible:ring-danger-text/40",
        link: "text-brand underline-offset-4 hover:underline",
      },
      size: {
        default: "h-8 gap-1.5 px-2.5 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2",
        xs: "h-6 gap-1 rounded-[min(var(--radius-md),10px)] px-2 text-xs in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-7 gap-1 rounded-[min(var(--radius-md),12px)] px-2.5 text-[0.8rem] in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3.5",
        lg: "h-9 gap-1.5 px-2.5 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2",
        icon: "size-8",
        "icon-xs":
          "size-6 rounded-[min(var(--radius-md),10px)] in-data-[slot=button-group]:rounded-lg [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-7 rounded-[min(var(--radius-md),12px)] in-data-[slot=button-group]:rounded-lg",
        "icon-lg": "size-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

function Button({
  className,
  variant = "default",
  size = "default",
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return (
    <ButtonPrimitive
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  );
}

export { Button, buttonVariants };
