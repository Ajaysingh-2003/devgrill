import { type ClassValue, clsx } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

/**
 * tailwind-merge must know DevGrill's custom font-size names. Otherwise it reads
 * `text-body` as a colour and silently drops it when `text-fg` also appears.
 * Keep in sync with "type" in packages/tokens/tokens.json.
 */
const twMerge = extendTailwindMerge({
  extend: {
    theme: {
      text: [
        "display-2xl",
        "display-xl",
        "display-lg",
        "heading-lg",
        "heading-md",
        "body-lg",
        "body",
        "label",
        "caption",
        "mono",
        "mono-sm",
        "stat",
      ],
      radius: ["xs", "sm", "md", "lg"],
      shadow: ["float", "overlay"],
      ease: ["standard", "enter", "exit"],
    },
  },
});

/** Merge Tailwind class lists, letting later classes win (shadcn convention). */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
