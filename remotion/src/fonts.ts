// Deterministic Playfair Display via Remotion's Google Fonts loader. loadFont()
// registers with Remotion's font-ready gate so the render waits for the font
// before capturing frames — no fallback-flash, no network race at render time.
import { loadFont } from "@remotion/google-fonts/PlayfairDisplay";

export const { fontFamily: playfair } = loadFont("normal", {
  weights: ["400", "500", "700"],
  subsets: ["latin"],
});

// Italic is a separate style axis; load it too so <i>/font-style:italic renders
// in the real face rather than a synthetic slant.
loadFont("italic", { weights: ["400", "500"], subsets: ["latin"] });
