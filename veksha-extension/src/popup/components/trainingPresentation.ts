import type { TrainingOutcome } from "../../shared/types";

export function feedbackTone(outcome: TrainingOutcome): string {
  switch (outcome) {
    case "correct": return "feedback-correct";
    case "incorrect":
    case "garbage": return "feedback-incorrect";
    default: return "feedback-vague";
  }
}
