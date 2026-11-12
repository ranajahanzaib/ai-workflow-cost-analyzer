import { describe, expect, it } from "vitest";
import { money, percent } from "./format";

describe("display formatting", () => {
  it("formats USD amounts to cents", () =>
    expect(money("0.4167")).toBe("$0.42"));
  it("keeps missing amounts explicit", () => expect(money(null)).toBe("N/A"));
  it("formats ratios as percentages", () =>
    expect(percent("0.83")).toBe("83.0%"));
  it("keeps missing rates explicit", () => expect(percent(null)).toBe("N/A"));
});
