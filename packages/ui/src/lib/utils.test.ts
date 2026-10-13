import { describe, expect, it } from "vitest";
import { cn } from "./utils";

describe("cn", () => {
  it("keeps a custom font size next to a semantic text colour", () => {
    expect(cn("text-body text-fg")).toBe("text-body text-fg");
    expect(cn("text-stat", "text-fg-muted")).toBe("text-stat text-fg-muted");
  });

  it("lets later classes of the same group win", () => {
    expect(cn("text-body", "text-caption")).toBe("text-caption");
    expect(cn("bg-surface", "bg-raised")).toBe("bg-raised");
    expect(cn("rounded-sm", "rounded-md")).toBe("rounded-md");
  });

  it("handles conditional classes", () => {
    expect(cn("px-2", false && "px-4", undefined, ["py-1"])).toBe("px-2 py-1");
  });
});
