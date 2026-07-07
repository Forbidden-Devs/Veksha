/// <reference types="vite/client" />
/// <reference types="chrome" />

/** Build target, injected via `define` in vite.config.ts. */
declare const __BROWSER__: "chrome" | "firefox";

declare module "*.css?inline" {
  const css: string;
  export default css;
}
