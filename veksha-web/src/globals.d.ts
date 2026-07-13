/**
 * Build-time constants of the extension build (vite define). The web app has
 * no such defines — shared code must guard with `typeof __BROWSER__`.
 */
declare const __BROWSER__: "chrome" | "firefox" | undefined;
declare const __DEV_BUILD__: boolean;
