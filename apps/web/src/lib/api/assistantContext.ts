export type AssistantBench =
  | "SmartBrief"
  | "Red-Teamer"
  | "Deck"
  | "Researcher"
  | "Reviewer"
  | "Home";

export interface AssistantReference {
  type: "analysis";
  id: string;
  label: string;
}

export interface AssistantContext {
  bench: AssistantBench;
  reference?: AssistantReference;
}