// Source: shadcn/ui registry (base-nova) "skeleton", adapted to DevGrill tokens.
import { cn } from "@devgrill/ui/lib/utils";

function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div data-slot="skeleton" className={cn("animate-pulse rounded-md bg-raised", className)} {...props} />
  );
}

export { Skeleton };
