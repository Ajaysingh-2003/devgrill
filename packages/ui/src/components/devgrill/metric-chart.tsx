"use client";

import { useEffect, useRef } from "react";
import uPlot, { type AlignedData, type Options } from "uplot";
import "uplot/dist/uPlot.min.css";
import { cn } from "@devgrill/ui/lib/utils";

export type ChartSeries = {
  label: string;
  values: (number | null)[];
  /** Categorical slot 1–8 from the chart palette. */
  color?: 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8;
};

export type ChartMarker = { at: number; label: string };

export type MetricChartProps = {
  title: string;
  /** Text alternative for the canvas, e.g. "p99 latency rose from 120 ms to 4.2 s after 20:00". */
  summary: string;
  /** Unix seconds, one per point. */
  timestamps: number[];
  series: ChartSeries[];
  /** Formats the headline value and y-axis ticks. */
  format?: (value: number) => string;
  threshold?: { value: number; label: string };
  markers?: ChartMarker[];
  height?: number;
  /** Charts sharing a key share the crosshair. */
  syncKey?: string;
  className?: string;
};

const cssVar = (name: string) =>
  getComputedStyle(document.documentElement).getPropertyValue(`--${name}`).trim();

/**
 * Time-series chart for incident dashboards. New data snaps (no tweening): during an
 * incident, motion on streaming data is noise.
 */
export function MetricChart({
  title,
  summary,
  timestamps,
  series,
  format = (v) => String(Math.round(v)),
  threshold,
  markers = [],
  height = 140,
  syncKey,
  className,
}: MetricChartProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<uPlot | null>(null);
  const dataRef = useRef<AlignedData>([timestamps, ...series.map((s) => s.values)]);
  dataRef.current = [timestamps, ...series.map((s) => s.values)];

  // Build (and rebuild on theme change) the chart.
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    const build = () => {
      chartRef.current?.destroy();
      const axisColor = cssVar("text-subtle");
      const gridColor = cssVar("border");
      // next/font sets --font-code on <html>; canvas needs a concrete family list.
      const code = getComputedStyle(document.documentElement).getPropertyValue("--font-code").trim();
      const mono = code ? `${code}, ui-monospace, monospace` : "ui-monospace, monospace";
      const thresholdColor = cssVar("chart-threshold");
      const breach = cssVar("chart-breach");
      const markerColor = cssVar("text-muted");
      const labelBg = cssVar("surface");

      const opts: Options = {
        width: Math.max(host.clientWidth, 120),
        height,
        legend: { show: false },
        cursor: syncKey ? { sync: { key: syncKey } } : {},
        scales: { x: { time: true } },
        axes: [
          {
            stroke: axisColor,
            grid: { show: false },
            ticks: { stroke: gridColor, width: 1, size: 4 },
            font: `11px ${mono}`,
            size: 28,
            // Incidents span minutes to hours: 24-hour HH:MM only, no date line.
            values: (_u, ticks) =>
              ticks.map((t) =>
                new Date(t * 1000).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                  hour12: false,
                }),
              ),
          },
          {
            stroke: axisColor,
            grid: { stroke: gridColor, width: 1 },
            ticks: { show: false },
            font: `11px ${mono}`,
            size: 48,
            values: (_u, ticks) => ticks.map((t) => format(t)),
          },
        ],
        series: [
          {},
          ...series.map((s) => ({
            label: s.label,
            stroke: cssVar(`chart-${s.color ?? 1}`),
            width: 1.75,
            points: { show: false },
          })),
        ],
        hooks: {
          draw: [
            (u) => {
              const ctx = u.ctx;
              const { left, top, width, height: h } = u.bbox;
              const dpr = devicePixelRatio || 1;
              ctx.save();
              if (threshold) {
                const y = u.valToPos(threshold.value, "y", true);
                ctx.fillStyle = breach;
                ctx.fillRect(left, top, width, Math.max(0, y - top));
                ctx.strokeStyle = thresholdColor;
                ctx.lineWidth = 1 * dpr;
                ctx.setLineDash([4 * dpr, 4 * dpr]);
                ctx.beginPath();
                ctx.moveTo(left, y);
                ctx.lineTo(left + width, y);
                ctx.stroke();
                if (threshold.label) {
                  // Name the line (e.g. "SLO 500 ms") at its right end, on a knock-out.
                  ctx.font = `${10 * dpr}px ${mono}`;
                  ctx.textAlign = "right";
                  ctx.textBaseline = "bottom";
                  const w = ctx.measureText(threshold.label).width + 6 * dpr;
                  const x = left + width - 2 * dpr;
                  ctx.fillStyle = labelBg;
                  ctx.fillRect(x - w, y - 14 * dpr, w, 12 * dpr);
                  ctx.fillStyle = markerColor;
                  ctx.fillText(threshold.label, x - 3 * dpr, y - 3 * dpr);
                }
              }
              ctx.setLineDash([1 * dpr, 3 * dpr]);
              ctx.strokeStyle = markerColor;
              ctx.font = `${10 * dpr}px ${mono}`;
              // uPlot leaves its axis alignment on the context; set ours explicitly.
              ctx.textAlign = "left";
              ctx.textBaseline = "top";
              const pad = 3 * dpr;
              const lineH = 14 * dpr;
              markers.forEach((marker, i) => {
                const x = u.valToPos(marker.at, "x", true);
                if (x < left || x > left + width) return;
                ctx.beginPath();
                ctx.moveTo(x, top);
                ctx.lineTo(x, top + h);
                ctx.stroke();
                // Labels sit beside their line (flipped left near the right edge), staggered so
                // close events (deploy, then sale) stay readable, on a knock-out over the series.
                const w = ctx.measureText(marker.label).width + pad * 2;
                const lx = x + 2 * dpr + w > left + width ? x - 2 * dpr - w : x + 2 * dpr;
                const ly = top + 2 * dpr + i * lineH;
                ctx.fillStyle = labelBg;
                ctx.fillRect(lx, ly, w, lineH - 2 * dpr);
                ctx.fillStyle = markerColor;
                ctx.fillText(marker.label, lx + pad, ly + 1 * dpr);
              });
              ctx.restore();
            },
          ],
        },
      };
      chartRef.current = new uPlot(opts, dataRef.current, host);
    };

    build();
    const resize = new ResizeObserver(() => {
      chartRef.current?.setSize({ width: Math.max(host.clientWidth, 120), height });
    });
    resize.observe(host);
    // Theme switches change the resolved colours: rebuild.
    const themeObserver = new MutationObserver(build);
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });

    return () => {
      resize.disconnect();
      themeObserver.disconnect();
      chartRef.current?.destroy();
      chartRef.current = null;
    };
    // Structure changes rebuild; data changes go through setData below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [height, syncKey, series.length, threshold?.value, markers.length]);

  // Data updates snap in without rebuilding.
  useEffect(() => {
    chartRef.current?.setData(dataRef.current);
  }, [timestamps, series]);

  const latest = series[0]?.values.findLast((v) => v !== null);
  return (
    <figure className={cn("flex flex-col gap-1", className)}>
      <figcaption className="flex items-baseline justify-between gap-3 px-1">
        <span className="text-label font-medium text-fg-muted">{title}</span>
        {latest !== undefined && latest !== null ? (
          <span className="font-mono text-heading-md font-semibold text-fg tabular-nums">
            {format(latest)}
          </span>
        ) : null}
        <span className="sr-only">. {summary}</span>
      </figcaption>
      <div ref={hostRef} aria-hidden="true" className="w-full" style={{ height }} />
    </figure>
  );
}
