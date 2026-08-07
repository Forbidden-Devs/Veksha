import { afterEach, describe, expect, it, vi } from "vitest";
import { adminApi, normalizedCode } from "./api";

afterEach(() => vi.unstubAllGlobals());

describe("normalizedCode", () => {
  it("normalizes codes exactly as the backend does", () => {
    expect(normalizedCode("  welcome-30 ")).toBe("WELCOME-30");
  });
});

describe("adminApi.setPromoPaused", () => {
  it("normalizes the code and sends the requested state", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ ok: true, code: "WELCOME-30", paused: false }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ));
    vi.stubGlobal("fetch", fetchMock);

    await adminApi.setPromoPaused("secret", " welcome-30 ", false);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/api/billing/promo/WELCOME-30/pause",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ paused: false }),
        headers: expect.objectContaining({ "X-Veksha-Admin-Secret": "secret" }),
      }),
    );
  });
});
