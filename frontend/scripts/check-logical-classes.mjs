import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

/**
 * Matches physical-direction Tailwind CSS utilities (with optional variant prefixes like `md:` or `hover:`
 * and optional negative/important modifiers like `-` or `!`):
 * - ml-*, mr-*, pl-*, pr-*, left-*, right-*
 * - text-left, text-right
 * - rounded-l-*, rounded-r-*, rounded-tl-*, rounded-tr-*, rounded-bl-*, rounded-br-* (and bare rounded-l, rounded-r)
 * - border-l-*, border-r-* (and bare border-l, border-r)
 */
export const PHYSICAL_CLASS_REGEX =
  /(?:^|(?<=[\s"'`{(,;]))(?:[\w-[\]/]+:)*!?(?:-?(?:ml|mr|pl|pr|left|right)-[\w./[\]%$-]+|text-(?:left|right)(?=$|[\s"'`}),;])|rounded-(?:l|r|tl|tr|bl|br)(?:-[\w./[\]%$-]+|(?=$|[\s"'`}),;]))|border-(?:l|r)(?:-[\w./[\]%$-]+|(?=$|[\s"'`}),;])))/g;

/**
 * Strip JS/TS comments before scanning so explanations in comments do not trigger false positives.
 * @param {string} source
 * @returns {string}
 */
function stripComments(source) {
  return source.replace(/\/\*[\s\S]*?\*\/|\/\/.*/g, "");
}

/**
 * Returns all physical-direction Tailwind class tokens found in the given text.
 * @param {string} input
 * @returns {string[]}
 */
export function findPhysicalClasses(input) {
  const cleaned = stripComments(input);
  const matches = cleaned.match(PHYSICAL_CLASS_REGEX);
  return matches ? [...matches] : [];
}

/**
 * Returns true if the input contains any physical-direction Tailwind class.
 * @param {string} input
 * @returns {boolean}
 */
export function hasPhysicalClasses(input) {
  return findPhysicalClasses(input).length > 0;
}

/**
 * Recursively collects `.ts` and `.tsx` files under `dir`.
 * @param {string} dir
 * @returns {string[]}
 */
function collectSourceFiles(dir) {
  /** @type {string[]} */
  const results = [];
  if (!fs.existsSync(dir)) {
    return results;
  }
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...collectSourceFiles(fullPath));
    } else if (
      entry.isFile() &&
      (entry.name.endsWith(".ts") || entry.name.endsWith(".tsx")) &&
      !entry.name.endsWith(".d.ts")
    ) {
      results.push(fullPath);
    }
  }
  return results;
}

const currentFilePath = fileURLToPath(import.meta.url);
const isMain =
  Boolean(process.argv[1]) &&
  path.resolve(process.argv[1]) === path.resolve(currentFilePath);

if (isMain) {
  const srcDir = path.resolve(path.dirname(currentFilePath), "../src");
  const files = collectSourceFiles(srcDir);
  /** @type {Array<{ file: string; classes: string[] }>} */
  const violations = [];

  for (const file of files) {
    const content = fs.readFileSync(file, "utf8");
    const found = findPhysicalClasses(content);
    if (found.length > 0) {
      violations.push({
        file: path.relative(process.cwd(), file),
        classes: found,
      });
    }
  }

  if (violations.length > 0) {
    console.error(
      "RTL guard failed: physical-direction Tailwind classes found. Use logical equivalents (ms-, me-, ps-, pe-, start-, end-, text-start, text-end, rounded-s-, rounded-e-, border-s-, border-e-):",
    );
    for (const v of violations) {
      console.error(`  ${v.file}: ${v.classes.join(", ")}`);
    }
    process.exit(1);
  }
}
