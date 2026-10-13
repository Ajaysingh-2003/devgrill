import { cn } from "@devgrill/ui/lib/utils";

/** Topic or track mastery, 0–100. A ring, not a bar, so it reads as "share of the whole". */
export function MasteryRing({
  value,
  label,
  size = 40,
  className,
}: {
  value: number;
  label: string;
  size?: number;
  className?: string;
}) {
  const clamped = Math.max(0, Math.min(100, value));
  const stroke = size >= 56 ? 4 : 3;
  const r = (size - stroke) / 2;
  const circumference = 2 * Math.PI * r;
  return (
    <span
      role="img"
      aria-label={`${label}: ${clamped}% mastered`}
      className={cn("relative inline-grid shrink-0 place-items-center", className)}
      style={{ width: size, height: size }}
    >
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        className="-rotate-90"
        aria-hidden="true"
      >
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--raised)" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="var(--brand)"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - clamped / 100)}
        />
      </svg>
      <span
        aria-hidden="true"
        className={cn(
          "absolute font-mono font-semibold text-fg tabular-nums",
          size >= 56 ? "text-mono" : "text-[0.625rem]",
        )}
      >
        {clamped}
      </span>
    </span>
  );
}
