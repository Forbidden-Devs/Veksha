/// <reference types="vite/client" />
/// <reference types="chrome" />

/** Build target, injected via `define` in vite.config.ts. */
declare const __BROWSER__: "chrome" | "firefox";
declare const __DEV_BUILD__: boolean;

declare module "*.css?inline" {
  const css: string;
  export default css;
}
