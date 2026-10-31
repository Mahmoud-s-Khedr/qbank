// Pages move rendered → extracted → validated, so a stage's progress counts every page
// that has reached it *or a later stage* (otherwise "rendered" drops back to 0).
const PIPELINE_ORDER = ["rendered", "extracted", "validated"] as const;

export function cumulativeStageCount(
  counts: Partial<Record<string, number>>,
  stage: "rendered" | "extracted" | "validated" | "failed",
): number {
  if (stage === "failed") return counts.failed ?? 0;
  const from = PIPELINE_ORDER.indexOf(stage);
  return PIPELINE_ORDER.slice(from).reduce(
    (sum, key) => sum + (counts[key] ?? 0),
    0,
  );
}
