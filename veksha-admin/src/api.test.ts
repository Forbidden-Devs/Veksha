import { describe, expect, it } from "vitest";
import { normalizedCode } from "./api";

describe("normalizedCode", () => {
  it("normalizes codes exactly as the backend does", () => {
    expect(normalizedCode("  welcome-30 ")).toBe("WELCOME-30");
  });
});
