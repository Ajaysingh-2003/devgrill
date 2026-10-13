/**
 * Zero-JS SVG line chart for static surfaces (landing page, profile). Live incident charts use
 * MetricChart (uPlot). Colours come from tokens, so it follows the theme without JavaScript.
 */
export function Sparkline({
  values,
  width = 320,
  height = 96,
  threshold,
  marker,
  label,
  color = "var(--chart-1)",
  className,
}: {
  values: number[];
  width?: number;
  height?: number;
  threshold?: number;
  /** Index of a vertical marker (e.g. the deploy). */
  marker?: number;
  label: string;
  color?: string;
  className?: string;
}) {
  const max = Math.max(...values, threshold ?? 0) * 1.08;
  const min = Math.min(...values, 0);
  const x = (i: number) => (i / (values.length - 1)) * width;
  const y = (v: number) => height - ((v - min) / (max - min)) * height;
  const d = values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(" ");
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={label}
      className={className}
    >
      {threshold !== undefined ? (
        <>
          <rect x="0" y="0" width={width} height={y(threshold)} fill="var(--chart-breach)" />
          <line
            x1="0"
            x2={width}
            y1={y(threshold)}
            y2={y(threshold)}
            stroke="var(--chart-threshold)"
            strokeDasharray="4 4"
            vectorEffect="non-scaling-stroke"
          />
        </>
      ) : null}
      {marker !== undefined ? (
        <line
          x1={x(marker)}
          x2={x(marker)}
          y1="0"
          y2={height}
          stroke="var(--text-subtle)"
          strokeDasharray="1 3"
          vectorEffect="non-scaling-stroke"
        />
      ) : null}
      <path
        d={d}
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
