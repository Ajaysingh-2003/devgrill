/** Static placeholder while route params resolve. No shimmer: it is rarely seen (pages are prerendered). */
export function PageSkeleton({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" aria-label={label} className="flex flex-col gap-6">
      <div className="h-4 w-48 rounded-xs bg-raised" />
      <div className="h-9 w-2/3 max-w-xl rounded-sm bg-raised" />
      <div className="h-4 w-full max-w-2xl rounded-xs bg-raised" />
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="h-28 rounded-md bg-raised" />
        <div className="h-28 rounded-md bg-raised" />
      </div>
    </div>
  );
}
