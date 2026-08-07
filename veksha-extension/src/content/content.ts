import { startPageRuntime } from "./page-runtime";

type RuntimeWindow = Window & { __vekshaPageRuntimeV2?: Promise<void> };

const runtimeWindow = window as RuntimeWindow;
runtimeWindow.__vekshaPageRuntimeV2 ??= startPageRuntime().catch((error: unknown) => {
  delete runtimeWindow.__vekshaPageRuntimeV2;
  console.error("[Veksha] page runtime failed to start", error);
});
