import { ImageResponse } from "next/og";
import { BRAND } from "@devgrill/config/brand";

export const alt = `${BRAND.name}: ${BRAND.tagline}`;
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

/**
 * Share card template (Arcade layer). Hex values: OG renderers need plain colours; they mirror
 * the tokens (graphite-950, paper canvas, signal brand, volt). Phase 9 adds per-result cards.
 */
export default function OpengraphImage() {
  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        padding: 72,
        background: "#fcfaf6",
        color: "#221f1b",
        fontFamily: "sans-serif",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <div style={{ width: 56, height: 9, borderRadius: 5, background: "#00768c" }} />
          <div style={{ width: 44, height: 9, borderRadius: 5, background: "#221f1b" }} />
          <div style={{ width: 33, height: 9, borderRadius: 5, background: "#221f1b", opacity: 0.72 }} />
          <div style={{ width: 22, height: 9, borderRadius: 5, background: "#221f1b", opacity: 0.48 }} />
        </div>
        <div style={{ fontSize: 40, fontWeight: 700 }}>{BRAND.name}</div>
      </div>
      <div style={{ fontSize: 76, fontWeight: 800, lineHeight: 1.02, letterSpacing: -2, maxWidth: 960 }}>
        {BRAND.tagline}
      </div>
      <div style={{ display: "flex", gap: 16, fontSize: 28 }}>
        <div
          style={{
            padding: "10px 18px",
            borderRadius: 8,
            background: "#b0d753",
            color: "#221f1b",
            fontWeight: 700,
          }}
        >
          Live outages
        </div>
        <div
          style={{
            padding: "10px 18px",
            borderRadius: 8,
            background: "#dbf2f6",
            color: "#156874",
            fontWeight: 700,
          }}
        >
          Real systems, real fixes
        </div>
      </div>
    </div>,
    size,
  );
}
