import { describe, expect, it } from "vitest";
import {
  findPhysicalClasses,
  hasPhysicalClasses,
} from "../../scripts/check-logical-classes.mjs";

function c(...parts: string[]): string {
  return parts.join("-");
}

describe("RTL logical classes guard", () => {
  it("fails on physical spacing classes", () => {
    const ml2 = c("ml", "2");
    const mr4 = c("mr", "4");
    const pl3 = c("pl", "3");
    const pr1 = c("pr", "1");

    expect(hasPhysicalClasses(`flex ${ml2} items-center`)).toBe(true);
    expect(findPhysicalClasses(`flex ${ml2} ${mr4} ${pl3} ${pr1}`)).toEqual([
      ml2,
      mr4,
      pl3,
      pr1,
    ]);
  });

  it("fails on responsive/state variants and physical alignment/borders/rounding", () => {
    const mdMl2 = `md:${c("ml", "2")}`;
    const hoverPr4 = `hover:${c("pr", "4")}`;
    const left0 = c("left", "0");
    const right2 = c("right", "2");
    const textLeft = c("text", "left");
    const textRight = c("text", "right");
    const roundedLMd = c("rounded", "l", "md");
    const roundedRLg = c("rounded", "r", "lg");
    const borderL2 = c("border", "l", "2");
    const borderR = c("border", "r");

    const sample = `<div className="${[
      mdMl2,
      hoverPr4,
      left0,
      right2,
      textLeft,
      textRight,
      roundedLMd,
      roundedRLg,
      borderL2,
      borderR,
    ].join(" ")}" />`;

    expect(hasPhysicalClasses(sample)).toBe(true);
    expect(findPhysicalClasses(sample)).toEqual([
      mdMl2,
      hoverPr4,
      left0,
      right2,
      textLeft,
      textRight,
      roundedLMd,
      roundedRLg,
      borderL2,
      borderR,
    ]);
  });

  it("passes on logical Tailwind equivalents like ms-2, me-4, ps-3, pe-1, start-0, end-2, text-start", () => {
    const sample =
      '<div className="flex ms-2 md:ms-4 me-2 ps-3 pe-1 start-0 end-2 text-start text-end rounded-s-md rounded-e-lg border-s-2 border-e" />';
    expect(hasPhysicalClasses(sample)).toBe(false);
    expect(findPhysicalClasses(sample)).toEqual([]);
  });

  it("ignores physical class names mentioned inside comments", () => {
    const ml2 = c("ml", "2");
    const textLeft = c("text", "left");
    const mr4 = c("mr", "4");
    const sample = `
      // Avoid ${ml2} and ${textLeft} here
      /* Also avoid ${mr4} */
      export const cls = "ms-2 ps-4 text-start";
    `;
    expect(hasPhysicalClasses(sample)).toBe(false);
  });
});
