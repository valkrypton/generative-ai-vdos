// Palette shared by every composition template. The Python compose stage passes
// a palette derived from the shot plan's `music_mood`, so cards feel connected to
// the video they bookend. All fields are plain CSS colors.

export type Palette = {
  bg1: string; // gradient top
  bg2: string; // gradient bottom
  fg: string; // primary text
  accent: string; // subheading / attribution
  glow: string; // soft radial glow color (rgba)
};

export const DEFAULT_PALETTE: Palette = {
  bg1: "#0f0b1e",
  bg2: "#3a2740",
  fg: "#f6ecd6",
  accent: "#f0b563",
  glow: "rgba(255,214,140,0.28)",
};

// Keep in sync with pipeline/compose/__init__.py MOOD_PALETTES.
export const MOOD_PALETTES: Record<string, Palette> = {
  calm: { bg1: "#0d1b2a", bg2: "#2a4a5c", fg: "#eaf4f4", accent: "#8fd0c8", glow: "rgba(143,208,200,0.22)" },
  upbeat: { bg1: "#231533", bg2: "#7a2f6a", fg: "#fdeff6", accent: "#ffb84d", glow: "rgba(255,184,77,0.26)" },
  dramatic: { bg1: "#0b0b12", bg2: "#3a1f22", fg: "#f4ead6", accent: "#e0714a", glow: "rgba(224,113,74,0.24)" },
  mysterious: { bg1: "#0a0f1e", bg2: "#241a3a", fg: "#e8e6f4", accent: "#a88fe0", glow: "rgba(168,143,224,0.22)" },
  inspiring: { bg1: "#0f0b1e", bg2: "#4a2f52", fg: "#f6ecd6", accent: "#f0b563", glow: "rgba(255,214,140,0.28)" },
};

import { playfair } from "./fonts";

export const serifStack = `${playfair}, Georgia, "Times New Roman", Cambria, serif`;
