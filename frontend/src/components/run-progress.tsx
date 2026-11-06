import type { Run } from "@/lib/types";

const labels: Record<string, string> = {
  queued: "Queued — waiting for a worker",
  planning: "Planning your story",
  writing: "Writing scenes and dialogue",
  evaluating: "Evaluating the first draft",
  revising: "Revising from the feedback",
  final_evaluation: "Evaluating the revised draft",
  saving: "Saving your story",
  retry_wait: "Waiting to retry after a temporary error",
};
const stages = [
  "planning",
  "writing",
  "evaluating",
  "revising",
  "final_evaluation",
  "saving",
];

export default function RunProgress({ run }: { run: Run }) {
  const current = stages.indexOf(run.stage);
  return (
    <section className="job-progress" aria-label="Generation progress">
      <p role="status" aria-live="polite">
        <span className="spinner" />{" "}
        {labels[run.stage] ?? "Generating your story"}
      </p>
      <ol>
        {stages.map((stage, index) => (
          <li
            key={stage}
            aria-current={stage === run.stage ? "step" : undefined}
            className={index === current ? "current" : ""}
          >
            {labels[stage]}
            {stage === "revising" || stage === "final_evaluation"
              ? " (if needed)"
              : ""}
          </li>
        ))}
      </ol>
      <p className="fine-print">
        {run.attempt ? `Attempt ${run.attempt} of 3. ` : "Your job is saved. "}
        You can leave or refresh this page. Reopen this story from your library
        to follow its progress.
        {run.stage === "retry_wait" && run.available_at
          ? ` Next attempt available after ${new Date(run.available_at).toLocaleTimeString()}.`
          : ""}
      </p>
    </section>
  );
}
