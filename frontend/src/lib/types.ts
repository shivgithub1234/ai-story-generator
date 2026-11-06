export type StoryInput = {
  premise: string;
  genre: string;
  language: string;
  target_words: number;
  tone: string | null;
};
export type Rating = {
  score: number;
  explanation: string;
  evidence: string;
  scene_numbers: number[];
};
export const dimensions = {
  narrative_coherence: "Narrative coherence",
  character_consistency: "Character consistency",
  repetition_avoidance: "Freshness & variety",
  language_quality: "Language quality",
  instruction_adherence: "Following your brief",
} as const;
export type Report = {
  overall_score: number;
  needs_revision: boolean;
  assessment: Record<keyof typeof dimensions, Rating> & {
    summary: string;
    revision_suggestions: string[];
  };
};
export type Script = {
  title: string;
  scenes: {
    heading: string;
    narration: string;
    dialogue: { speaker: string; text: string }[];
  }[];
};
export type Output = {
  script: Script;
  initial_script: Script;
  evaluation: Report;
  initial_evaluation: Report;
  final_text: string;
  revision_count: number;
  stop_reason: string;
  is_demo: boolean;
  warnings: string[];
  outline: {
    title: string;
    setting: string;
    conflict: string;
    scene_beats: string[];
    characters: { name: string; goal: string; traits: string }[];
  };
};
export type Run = {
  id: string;
  status: "running" | "completed" | "failed";
  started_at: string;
  error_code: string | null;
  output: Output | null;
};
export type StorySummary = {
  id: string;
  title: string;
  version: number;
  created_at: string;
};
export type Story = StorySummary & {
  request: StoryInput;
  edited_text: string | null;
  latest_run: Run | null;
};
