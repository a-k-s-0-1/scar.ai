import type { RewardExplanationRow } from "@/lib/types";

export function explainReward(
  components: Record<string, number> | null | undefined
): RewardExplanationRow[] {
  if (!components || Object.keys(components).length === 0) return [];

  const rows: RewardExplanationRow[] = [];
  const positive = new Set([
    "information_gain_reward",
    "evidence_quality_reward",
    "coverage_gain_reward",
    "contradiction_resolution_reward",
    "source_diversity_reward",
  ]);
  const labels: Record<string, string> = {
    information_gain_reward: "New claims and entities added this iteration",
    evidence_quality_reward: "Mean credibility of the evidence held",
    coverage_gain_reward: "Coverage of the question improved",
    contradiction_resolution_reward: "Contradictions resolved this iteration",
    source_diversity_reward: "New independent domains covered",
    redundancy_penalty: "Repeated findings already held",
    low_quality_source_penalty: "Low-credibility sources included",
    unnecessary_action_penalty: "Action repeated without new yield",
    time_cost_penalty: "Iteration time cost",
    budget_cost_penalty: "LLM-call budget consumed",
    unresolved_contradiction_penalty: "Open contradictions remain",
    v1_reward: "Legacy V1 reward signal",
    positive_total: "Sum of positive components",
    penalty_total: "Sum of penalty components",
    total: "Final reward",
  };

  for (const [key, value] of Object.entries(components)) {
    if (typeof value !== "number" || Number.isNaN(value)) continue;
    if (value === 0) continue;
    rows.push({
      component: key,
      value,
      reason: labels[key] ?? key,
      direction: positive.has(key) ? "credit" : "debit",
    });
  }

  return rows;
}
