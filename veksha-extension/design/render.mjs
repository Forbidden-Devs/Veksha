/**
 * render.mjs — Veksha squirrel brand art: logo, mascot, background pattern.
 * Everything is drawn as SVG strings and rasterized with resvg.
 *
 * Regenerate (from veksha-extension/):
 *   npm i --no-save @resvg/resvg-js
 *   node design/render.mjs
 *   ffmpeg -y -framerate 12 -i design/out/frames/mascot_%02d.png \
 *     -filter_complex "[0:v]split[a][b];[a]palettegen=reserve_transparent=1[p];[b][p]paletteuse=alpha_threshold=128:dither=bayer:bayer_scale=5" \
 *     -loop 0 source/squirrel.gif
 * Then copy design/out/logo_{16,48,128}.png over icons/icon*.png and
 * veksha-web/public/icons/, and design/out/back.png over source/back.png.
 */
import { Resvg } from "@resvg/resvg-js";
import { mkdirSync, writeFileSync } from "node:fs";

const OUT = new URL("./out/", import.meta.url).pathname;
mkdirSync(OUT, { recursive: true });

export function render(svg, width, file) {
  const r = new Resvg(svg, { fitTo: { mode: "width", value: width } });
  writeFileSync(OUT + file, r.render().asPng());
  console.log("wrote", file);
}

// ---------------------------------------------------------------------------
// LOGO — rounded-square gradient tile + white squirrel silhouette
// ---------------------------------------------------------------------------

export function logoSvg() {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">
  <defs>
    <linearGradient id="bg" x1="0" y1="1" x2="1" y2="0">
      <stop offset="0" stop-color="#ac96ef"/>
      <stop offset="1" stop-color="#fbc0ea"/>
    </linearGradient>
  </defs>
  <rect width="1024" height="1024" rx="232" fill="url(#bg)"/>
  <g fill="#ffffff">
    <!-- tail: big plume rising behind, curling forward at the top -->
    <path d="M 505 798
      C 700 815, 818 700, 828 545
      C 838 395, 762 258, 632 232
      C 552 218, 492 262, 500 326
      C 507 380, 560 402, 612 386
      C 648 374, 660 342, 648 316
      C 700 350, 700 450, 680 540
      C 662 636, 615 712, 528 742
      Z"/>
    <!-- haunch / body -->
    <ellipse cx="470" cy="650" rx="175" ry="158"/>
    <!-- head -->
    <circle cx="398" cy="400" r="118"/>
    <!-- ear tuft -->
    <path d="M 355 305 C 336 248, 352 202, 392 182 C 406 234, 426 262, 444 290 Z"/>
    <!-- foot -->
    <ellipse cx="420" cy="775" rx="95" ry="30"/>
  </g>
  <!-- eye -->
  <circle cx="352" cy="392" r="16" fill="url(#bg)"/>
  <!-- acorn in paws -->
  <g transform="translate(338 560) rotate(-12) scale(1.35)">
    <ellipse cx="0" cy="26" rx="30" ry="34" fill="url(#bg)"/>
    <path d="M -36 6 Q 0 -18 36 6 Q 38 22 0 20 Q -38 22 -36 6 Z" fill="url(#bg)"/>
  </g>
</svg>`;
}

// ---------------------------------------------------------------------------
// MASCOT — kawaii waving squirrel, 489x369, transparent background.
// t in [0,1) is the loop phase; static preview uses t=0.
// ---------------------------------------------------------------------------

const TAU = Math.PI * 2;

export function mascotSvg(t = 0) {
  const wave = Math.sin(t * TAU);            // waving arm
  const sway = Math.sin(t * TAU + 1.2);      // tail
  const bob = Math.sin(t * TAU + 0.6);       // head bob
  const armRot = -6 + 12 * wave;
  const tailRot = 3.2 * sway;
  const headRot = 2.4 * bob;
  const sparkle = (phase) => (0.45 + 0.55 * (0.5 + 0.5 * Math.sin(t * TAU * 2 + phase))).toFixed(3);
  const sparkleScale = (phase) => (0.8 + 0.25 * (0.5 + 0.5 * Math.sin(t * TAU * 2 + phase))).toFixed(3);

  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 489 369">
  <defs>
    <linearGradient id="tailg" x1="0" y1="1" x2="0.4" y2="0">
      <stop offset="0" stop-color="#f6c7d8"/>
      <stop offset="1" stop-color="#f9d9ba"/>
    </linearGradient>
  </defs>

  <!-- tail (drawn first, tucked behind the body) -->
  <g transform="translate(16 0) rotate(${tailRot.toFixed(2)} 310 370)">
    <path d="M 300 380
      C 380 372, 430 310, 438 230
      C 446 148, 412 84, 348 70
      C 300 60, 264 88, 272 122
      C 280 152, 318 162, 342 146
      C 352 190, 356 240, 344 288
      C 336 320, 320 356, 300 380 Z" fill="url(#tailg)"/>
    <path d="M 344 288 C 356 240 352 190 342 146 C 366 200 366 250 356 296 Q 350 292 344 288 Z"
      fill="#fdf0e2" opacity="0.5"/>
  </g>

  <!-- body -->
  <ellipse cx="235" cy="318" rx="94" ry="84" fill="#fdf4ea"/>

  <!-- dress -->
  <path d="M 148 302 Q 235 268 322 302 L 334 380 L 136 380 Z" fill="#f7c0d3"/>
  <path d="M 148 302 Q 235 268 322 302 Q 300 316 278 306 Q 256 320 235 308 Q 214 320 192 306 Q 170 316 148 302 Z"
    fill="#fbd9e4"/>

  <!-- resting arm + acorn -->
  <g>
    <ellipse cx="298" cy="290" rx="26" ry="34" transform="rotate(-30 298 290)" fill="#fdf4ea"/>
    <g transform="translate(318 292) rotate(14)">
      <ellipse cx="0" cy="10" rx="17" ry="20" fill="#cf9560"/>
      <path d="M -21 -2 Q 0 -16 21 -2 Q 22 8 0 7 Q -22 8 -21 -2 Z" fill="#9e6c44"/>
      <rect x="-2.4" y="-18" width="4.8" height="8" rx="2.4" fill="#9e6c44"/>
    </g>
  </g>

  <!-- head group -->
  <g transform="rotate(${headRot.toFixed(2)} 235 265)">
    <!-- ears: small upright rounded triangles with tufts -->
    <path d="M 164 42 C 160 26, 162 16, 168 4 C 174 18, 180 28, 188 40 Z" fill="#fdf4ea"/>
    <path d="M 138 112 C 128 74, 144 42, 172 34 C 196 42, 206 70, 200 102 C 180 86, 158 94, 138 112 Z" fill="#fdf4ea"/>
    <path d="M 152 96 C 148 72, 158 54, 172 48 C 186 56, 192 72, 188 92 C 176 82, 164 86, 152 96 Z" fill="#f8c8d2"/>
    <path d="M 306 42 C 310 26, 308 16, 302 4 C 296 18, 290 28, 282 40 Z" fill="#fdf4ea"/>
    <path d="M 332 112 C 342 74, 326 42, 298 34 C 274 42, 264 70, 270 102 C 290 86, 312 94, 332 112 Z" fill="#fdf4ea"/>
    <path d="M 318 96 C 322 72, 312 54, 298 48 C 284 56, 278 72, 282 92 C 294 82, 306 86, 318 96 Z" fill="#f8c8d2"/>
    <!-- head -->
    <circle cx="235" cy="180" r="102" fill="#fdf4ea"/>
    <!-- cheeks -->
    <ellipse cx="152" cy="216" rx="24" ry="15" fill="#f8bcc6"/>
    <ellipse cx="318" cy="216" rx="24" ry="15" fill="#f8bcc6"/>
    <!-- eyes: happy closed arcs -->
    <path d="M 172 184 Q 192 164 212 184" fill="none" stroke="#6b4a3f" stroke-width="7" stroke-linecap="round"/>
    <path d="M 258 184 Q 278 164 298 184" fill="none" stroke="#6b4a3f" stroke-width="7" stroke-linecap="round"/>
    <!-- nose -->
    <path d="M 228 200 Q 235 194 242 200 Q 240 208 235 209 Q 230 208 228 200 Z" fill="#e0958f"/>
    <!-- mouth -->
    <path d="M 215 213 Q 235 218 255 213 Q 252 242 235 242 Q 218 242 215 213 Z" fill="#9c4f57"/>
    <path d="M 224 232 Q 235 226 246 232 Q 243 240 235 240 Q 227 240 224 232 Z" fill="#f2a0ae"/>
  </g>

  <!-- waving arm -->
  <g transform="rotate(${armRot.toFixed(2)} 168 272)">
    <path d="M 150 280 C 118 252, 100 218, 102 186 C 104 172, 118 164, 132 170 C 152 196, 162 232, 178 268 Z" fill="#fdf4ea"/>
    <circle cx="112" cy="178" r="30" fill="#fdf4ea"/>
    <circle cx="112" cy="186" r="11" fill="#f3b7c1"/>
    <circle cx="96" cy="166" r="5.5" fill="#f3b7c1"/>
    <circle cx="111" cy="160" r="5.5" fill="#f3b7c1"/>
    <circle cx="126" cy="166" r="5.5" fill="#f3b7c1"/>
  </g>

  <!-- sparkles -->
  <g fill="#f5a9c4">
    ${[
      [56, 150, 0.0], [96, 88, 1.5], [420, 104, 2.8], [448, 182, 4.2], [386, 52, 5.4],
    ].map(([x, y, p]) => `<g transform="translate(${x} ${y}) scale(${sparkleScale(p)})" opacity="${sparkle(p)}">
      <path d="M 0 -16 C 2.6 -5 5 -2.6 16 0 C 5 2.6 2.6 5 0 16 C -2.6 5 -5 2.6 -16 0 C -5 -2.6 -2.6 -5 0 -16 Z"/>
    </g>`).join("\n    ")}
  </g>
</svg>`;
}

// ---------------------------------------------------------------------------
// main
// ---------------------------------------------------------------------------
render(logoSvg(), 512, "logo_512.png");
render(logoSvg(), 128, "logo_128.png");
render(logoSvg(), 48, "logo_48.png");
render(logoSvg(), 16, "logo_16.png");
render(mascotSvg(0), 489, "mascot_0.png");
render(mascotSvg(0.25), 489, "mascot_25.png");
render(mascotSvg(0.75), 489, "mascot_75.png");

// ---------------------------------------------------------------------------
// BACKGROUND PATTERN — light lavender sheet of doodles (squirrels, acorns,
// oak leaves, nuts…), 1024x1536 like the old bunny back.png.
// ---------------------------------------------------------------------------

// Deterministic pseudo-random so the pattern is reproducible.
function mulberry32(seed) {
  let a = seed;
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function patternSvg() {
  const rnd = mulberry32(20260707);
  const ids = [
    "squirrel", "acorn", "leaf", "nut", "tree", "heart",
    "sparkle", "cloud", "envelope", "mug", "mushroom", "book",
  ];
  const cellW = 128, cellH = 128;
  let uses = "";
  for (let cy = 0; cy < 12; cy++) {
    for (let cx = 0; cx < 8; cx++) {
      if (rnd() < 0.12) continue; // leave some air
      const id = ids[(cx + cy * 5 + Math.floor(rnd() * 3)) % ids.length];
      const x = cx * cellW + 44 + rnd() * 40 + (cy % 2 ? 32 : 0);
      const y = cy * cellH + 44 + rnd() * 40;
      const rot = (rnd() * 40 - 20).toFixed(1);
      const s = (0.8 + rnd() * 0.5).toFixed(2);
      uses += `<use href="#${id}" transform="translate(${x.toFixed(0)} ${y.toFixed(0)}) rotate(${rot}) scale(${s})"/>\n`;
    }
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1536">
  <defs>
    <g id="squirrel" fill="none" stroke="#b3a6e4" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
      <!-- head -->
      <circle cx="-13" cy="-9" r="7.5"/>
      <!-- ear -->
      <path d="M -16 -15 C -18 -20, -16 -24, -12 -26 C -11 -22, -9 -19, -7 -16"/>
      <!-- back + bottom -->
      <path d="M -17 -3 C -24 4, -21 15, -11 19 L 7 19"/>
      <!-- paw -->
      <path d="M -12 6 C -9 8, -9 11, -12 13"/>
      <!-- tail: rises behind, curls forward -->
      <path d="M 7 19 C 19 16, 25 5, 21 -7 C 18 -16, 8 -19, 4 -13 C 1 -8, 5 -3, 10 -5"/>
      <circle cx="-15" cy="-10" r="1.6" fill="#b3a6e4" stroke="none"/>
    </g>
    <g id="acorn" fill="none" stroke="#b3a6e4" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
      <path d="M -12 -4 Q 0 -12 12 -4 Q 13 2 0 1 Q -13 2 -12 -4 Z"/>
      <path d="M -9 1 C -9 10, -4 16, 0 18 C 4 16, 9 10, 9 1"/>
      <path d="M 0 -9 C 0 -13, 2 -16, 5 -18"/>
    </g>
    <g id="leaf" fill="none" stroke="#b3a6e4" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
      <path d="M 0 -18 C 8 -14, 12 -8, 10 -2 C 14 0, 14 6, 9 8 C 11 12, 8 17, 2 16 L 0 18 L -2 16 C -8 17, -11 12, -9 8 C -14 6, -14 0, -10 -2 C -12 -8, -8 -14, 0 -18 Z"/>
      <path d="M 0 -12 L 0 16"/>
    </g>
    <g id="nut" fill="none" stroke="#b3a6e4" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
      <path d="M -10 2 C -10 -6, -5 -12, 0 -14 C 5 -12, 10 -6, 10 2 C 10 9, 5 14, 0 14 C -5 14, -10 9, -10 2 Z"/>
      <path d="M -8 -6 Q 0 -10 8 -6"/>
    </g>
    <g id="tree" fill="none" stroke="#b3a6e4" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
      <path d="M 0 -20 C 10 -20, 16 -12, 14 -4 C 20 2, 16 12, 8 12 L -8 12 C -16 12, -20 2, -14 -4 C -16 -12, -10 -20, 0 -20 Z"/>
      <path d="M 0 12 L 0 22 M -6 22 L 6 22"/>
    </g>
    <g id="heart" fill="none" stroke="#b3a6e4" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
      <path d="M 0 12 C -14 2, -14 -10, -6 -12 C -2 -13, 0 -10, 0 -7 C 0 -10, 2 -13, 6 -12 C 14 -10, 14 2, 0 12 Z"/>
    </g>
    <g id="sparkle" fill="none" stroke="#b3a6e4" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
      <path d="M 0 -12 C 1.8 -4 4 -1.8 12 0 C 4 1.8 1.8 4 0 12 C -1.8 4 -4 1.8 -12 0 C -4 -1.8 -1.8 -4 0 -12 Z"/>
    </g>
    <g id="cloud" fill="none" stroke="#b3a6e4" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
      <path d="M -14 8 C -20 8, -20 -2, -12 -2 C -12 -10, 0 -12, 3 -5 C 10 -8, 17 -2, 14 4 C 18 8, 12 12, 8 8 Z"/>
    </g>
    <g id="envelope" fill="none" stroke="#b3a6e4" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
      <rect x="-16" y="-11" width="32" height="22" rx="3"/>
      <path d="M -14 -8 L 0 3 L 14 -8"/>
    </g>
    <g id="mug" fill="none" stroke="#b3a6e4" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
      <path d="M -12 -8 L -12 8 C -12 12, -8 14, -4 14 L 4 14 C 8 14, 12 12, 12 8 L 12 -8 Z"/>
      <path d="M 12 -4 C 18 -4, 18 6, 12 6"/>
      <path d="M -4 -14 C -4 -18, 0 -18, 0 -14 M 4 -14 C 4 -18, 8 -18, 8 -14" stroke-width="2.4"/>
    </g>
    <g id="mushroom" fill="none" stroke="#b3a6e4" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
      <path d="M -16 0 C -16 -10, -8 -16, 0 -16 C 8 -16, 16 -10, 16 0 Z"/>
      <path d="M -6 0 L -5 10 C -5 14, 5 14, 5 10 L 6 0"/>
      <circle cx="-6" cy="-8" r="1.6" fill="#b3a6e4" stroke="none"/>
      <circle cx="4" cy="-6" r="1.6" fill="#b3a6e4" stroke="none"/>
    </g>
    <g id="book" fill="none" stroke="#b3a6e4" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
      <path d="M 0 -10 C -5 -14, -12 -14, -16 -12 L -16 10 C -12 8, -5 8, 0 12 C 5 8, 12 8, 16 10 L 16 -12 C 12 -14, 5 -14, 0 -10 Z"/>
      <path d="M 0 -10 L 0 12"/>
    </g>
  </defs>
  <rect width="1024" height="1536" fill="#e6e0f6"/>
  <g opacity="0.5">
    ${uses}
  </g>
</svg>`;
}

render(patternSvg(), 1024, "back.png");

// mascot animation frames for the GIF
mkdirSync(OUT + "frames", { recursive: true });
const FRAMES = 12;
for (let i = 0; i < FRAMES; i++) {
  render(mascotSvg(i / FRAMES), 489, `frames/mascot_${String(i).padStart(2, "0")}.png`);
}
