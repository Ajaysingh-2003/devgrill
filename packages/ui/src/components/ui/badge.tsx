// Source: shadcn/ui registry (base-nova) "badge", adapted to DevGrill tokens.
import { mergeProps } from "@base-ui/react/merge-props";
import { useRender } from "@base-ui/react/use-render";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@devgrill/ui/lib/utils";

const badgeVariants = cva(
  "group/badge inline-flex h-5 w-fit shrink-0 items-center justify-center gap-1 overflow-hidden rounded-4xl border border-transparent px-2 py-0.5 text-xs font-medium whitespace-nowrap transition-all focus-visible:border-focus-ring focus-visible:ring-[3px] focus-visible:ring-focus-ring/50 has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 aria-invalid:border-danger-text aria-invalid:ring-danger-text/20 dark:aria-invalid:ring-danger-text/40 [&>svg]:pointer-events-none [&>svg]:size-3!",
  {
    variants: {
      variant: {
        default: "bg-brand text-on-brand [a]:hover:bg-brand/80",
        secondary: "bg-raised text-fg [a]:hover:bg-raised/80",
        destructive:
          "bg-danger-text/10 text-danger-text focus-visible:ring-danger-text/20 dark:bg-danger-text/20 dark:focus-visible:ring-danger-text/40 [a]:hover:bg-danger-text/20",
        outline: "border-border text-fg [a]:hover:bg-raised [a]:hover:text-fg-muted",
        ghost: "hover:bg-raised hover:text-fg-muted dark:hover:bg-raised/50",
        link: "text-brand underline-offset-4 hover:underline",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

function Badge({
  className,
  variant = "default",
  render,
  ...props
}: useRender.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return useRender({
    defaultTagName: "span",
    props: mergeProps<"span">(
      {
        className: cn(badgeVariants({ variant }), className),
      },
      props,
    ),
    render,
    state: {
      slot: "badge",
      variant,
    },
  });
}

export { Badge, badgeVariants };
