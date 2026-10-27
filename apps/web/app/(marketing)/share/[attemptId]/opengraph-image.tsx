import { ImageResponse } from "next/og";
import { shareCard } from "@devgrill/api-client";
import { BRAND } from "@devgrill/config/brand";
import { api, sevNumber, unwrap } from "@/lib/api";
import { shareHeading, stopwatch } from "@/lib/share";

export const alt = "A spoiler-free DevGrill result";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

/**
 * Hex values: OG renderers need plain colours. They mirror the light tokens (canvas, text,
 * text-muted, border, brand, and the sev1–sev4 fg/bg pairs).
 */
const C = { canvas: "#fcfaf6", text: "#221f1b", muted: "#5f5c57", border: "#e0dcd6", brand: "#00768c" };
const SEV = {
  1: { fg: "#a2292a", bg: "#f5eae9" },
  2: { fg: "#894820", bg: "#f5eae5" },
  3: { fg: "#5a4116", bg: "#f5ebdd" },
  4: { fg: "#156874", bg: "#dbf2f6" },
} as const;

/** Severity as four diamonds, filled by how hard it is (the SevGlyph, drawn for Satori). */
function Diamonds({ sev, color }: { sev: 1 | 2 | 3 | 4; color: string }) {
  return (
    <div style={{ display: "flex", gap: 10 }}>
      {[0, 1, 2, 3].map((i) => (
        <div
          key={i}
          style={{
            width: 22,
            height: 22,
            transform: "rotate(45deg)",
            background: i < 5 - sev ? color : "transparent",
            border: `3px solid ${color}`,
            opacity: i < 5 - sev ? 1 : 0.55,
          }}
        />
      ))}
    </div>
  );
}

export default async function ShareImage({ params }: { params: Promise<{ attemptId: string }> }) {
  const card = await unwrap(
    shareCard({ client: await api(), path: { attempt_id: (await params).attemptId } }),
  );
  const sev = sevNumber(card.difficulty);
  const hints =
    card.hints_used === 0 ? "No hints" : `${card.hints_used} hint${card.hints_used === 1 ? "" : "s"}`;
  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        padding: 72,
        background: C.canvas,
        color: C.text,
        fontFamily: "sans-serif",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 30 }}>
        <div style={{ fontWeight: 700 }}>{BRAND.name}</div>
        <div style={{ color: C.muted }}>{card.daily_on ? shareHeading(card) : "Incident drill"}</div>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 20,
            alignSelf: "flex-start",
            padding: "14px 22px",
            borderRadius: 10,
            background: SEV[sev].bg,
            color: SEV[sev].fg,
            fontSize: 36,
            fontWeight: 700,
          }}
        >
          <Diamonds sev={sev} color={SEV[sev].fg} />
          {`SEV${sev}`}
        </div>
        <div style={{ fontSize: 68, fontWeight: 800, lineHeight: 1.05, letterSpacing: -2, maxWidth: 1000 }}>
          {card.scenario_title}
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}>
        <div style={{ display: "flex", gap: 56 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <div style={{ fontSize: 26, color: C.muted }}>Fixed in</div>
            <div style={{ fontSize: 64, fontWeight: 800, fontFamily: "monospace" }}>
              {stopwatch(card.resolved_in_s)}
            </div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <div style={{ fontSize: 26, color: C.muted }}>Help</div>
            <div style={{ fontSize: 64, fontWeight: 800 }}>{hints}</div>
          </div>
        </div>
        <div style={{ fontSize: 26, color: C.brand, fontWeight: 700 }}>No spoilers. Can you beat it?</div>
      </div>
      <div
        style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 10, background: SEV[sev].fg }}
      />
    </div>,
    size,
  );
}
