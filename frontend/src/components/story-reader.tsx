"use client";

import { useEffect, useState } from "react";
import {
  dimensions,
  type Report,
  type Run,
  type Script,
  type Story,
} from "@/lib/types";

type Requester = <T>(path: string, options?: RequestInit) => Promise<T>;
type Props = {
  story: Story;
  request: Requester;
  busy: boolean;
  setBusy: (value: boolean) => void;
  onChange: (story: Story) => void;
  onDirtyChange: (dirty: boolean) => void;
};

export default function StoryReader({
  story,
  request,
  busy,
  setBusy,
  onChange,
  onDirtyChange,
}: Props) {
  const [tab, setTab] = useState("story");
  const [runs, setRuns] = useState<Run[]>([]);
  const [historyPage, setHistoryPage] = useState(0);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [historical, setHistorical] = useState<Run | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [title, setTitle] = useState(story.title);
  const [text, setText] = useState(
    story.edited_text ?? story.latest_run?.output?.final_text ?? "",
  );
  const run = historical ?? story.latest_run;
  const output = run?.output;
  const dirty =
    title !== story.title ||
    text !== (story.edited_text ?? story.latest_run?.output?.final_text ?? "");
  useEffect(() => {
    onDirtyChange(dirty);
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => {
      window.removeEventListener("beforeunload", warn);
      onDirtyChange(false);
    };
  }, [dirty, onDirtyChange]);
  useEffect(() => {
    const controller = new AbortController();
    setHistoryLoading(true);
    setHistoryError("");
    request<Run[]>(
      `stories/${story.id}/runs?limit=10&offset=${historyPage * 10}`,
      { signal: controller.signal },
    )
      .then((data) => {
        if (!controller.signal.aborted) setRuns(data);
      })
      .catch((err) => {
        if (!controller.signal.aborted)
          setHistoryError(
            err instanceof Error ? err.message : "Could not load history.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setHistoryLoading(false);
      });
    return () => controller.abort();
  }, [request, story.id, story.latest_run?.id, historyPage]);

  async function regenerate() {
    if (
      dirty &&
      !window.confirm(
        "Generate a new version and discard your unsaved editor changes?",
      )
    )
      return;
    setBusy(true);
    setError("");
    setNotice("");
    setHistorical(null);
    try {
      const updated = await request<Story>(`stories/${story.id}/runs`, {
        method: "POST",
      });
      onChange(updated);
      setText(
        updated.edited_text ?? updated.latest_run?.output?.final_text ?? "",
      );
      setTab("story");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generation failed.");
      try {
        onChange(await request<Story>(`stories/${story.id}`));
      } catch {
        /* Retain visible result. */
      }
    } finally {
      setBusy(false);
    }
  }
  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const updated = await request<Story>(`stories/${story.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          expected_version: story.version,
          title: title.trim(),
          edited_text: text,
        }),
      });
      onChange(updated);
      setTitle(updated.title);
      setNotice(
        "Your changes are saved. Manual edits have not been evaluated by AI.",
      );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not save your changes.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function reload() {
    setBusy(true);
    setError("");
    try {
      const updated = await request<Story>(`stories/${story.id}`);
      onChange(updated);
      setNotice(
        "Latest version loaded. Your unsaved editor text is preserved; compare before saving.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reload story.");
    } finally {
      setBusy(false);
    }
  }
  function download() {
    const value =
      tab === "edit"
        ? text
        : !historical && story.edited_text
          ? story.edited_text
          : output?.final_text;
    if (!value) return;
    const url = URL.createObjectURL(
      new Blob([value], { type: "text/plain;charset=utf-8" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `${story.title.replace(/[^a-zA-Z0-9 -]/g, "").slice(0, 70) || "story"}.txt`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="reader">
      <div className="reader-heading">
        <p className="eyebrow">
          {story.request.genre.replace("-", " ")} · {story.request.language} ·{" "}
          {story.request.target_words} WORD TARGET
        </p>
        <h1>{story.title}</h1>
        <p>{story.request.premise}</p>
      </div>
      <div className="reader-actions">
        <button
          className="secondary"
          disabled={busy || !output}
          onClick={download}
        >
          ↓ Download text
        </button>
        <button className="secondary" disabled={busy} onClick={reload}>
          Reload story
        </button>
        <button className="primary" disabled={busy} onClick={regenerate}>
          {busy ? "Working…" : "Generate a new version ↗"}
        </button>
      </div>
      <p className="fine-print">
        New versions start from your original brief. Your manual edits are kept
        separately.
      </p>
      {busy ? (
        <p role="status" className="progress-panel">
          <span className="spinner" /> Saving or generating your story. Please
          keep this page open.
        </p>
      ) : null}
      {error ? (
        <div role="alert" className="error">
          {error}
        </div>
      ) : null}
      {notice ? (
        <div role="status" className="notice">
          {notice}
        </div>
      ) : null}
      {historical ? (
        <div className="notice">
          Viewing a previous run from{" "}
          {new Date(historical.started_at).toLocaleString()}.{" "}
          <button className="text-button" onClick={() => setHistorical(null)}>
            Return to latest
          </button>
        </div>
      ) : null}
      {run?.status === "failed" ? (
        <div role="alert" className="error">
          This run could not finish ({run.error_code || "generation failed"}).
          You can generate a new version, or open an earlier result in History.
        </div>
      ) : run?.status === "running" ? (
        <div className="notice">
          This run is still marked as running. Use Reload story to check its
          status. Interrupted runs expire after ten minutes.
        </div>
      ) : null}
      <div className="reader-tabs" role="tablist" aria-label="Story views">
        {["story", "feedback", "outline", "edit", "history"].map((name) => (
          <button
            id={`tab-${name}`}
            role="tab"
            aria-selected={tab === name}
            aria-controls="reader-panel"
            key={name}
            className={tab === name ? "active" : ""}
            onClick={() => setTab(name)}
          >
            {name === "edit"
              ? "Your edits"
              : name[0].toUpperCase() + name.slice(1)}
          </button>
        ))}
      </div>
      <div id="reader-panel" role="tabpanel" aria-labelledby={`tab-${tab}`}>
        {tab === "story" ? (
          output ? (
            <div className="reading-grid">
              <article className="manuscript">
                {output.is_demo ? (
                  <div className="demo-label">Demo story · sample content</div>
                ) : null}
                {!historical && story.edited_text ? (
                  <>
                    <span className="pill">
                      Your edited version · not evaluated
                    </span>
                    <div className="plain-story">{story.edited_text}</div>
                    <details>
                      <summary>View AI-generated draft</summary>
                      <ScriptView script={output.script} />
                    </details>
                  </>
                ) : (
                  <ScriptView script={output.script} />
                )}
              </article>
              <aside className="score-summary">
                <p className="eyebrow">A SECOND PERSPECTIVE</p>
                <div className="big-score">
                  {output.evaluation.overall_score.toFixed(1)}
                  <small>/10</small>
                </div>
                <span
                  className={
                    output.evaluation.needs_revision ? "pill amber" : "pill"
                  }
                >
                  {output.evaluation.needs_revision
                    ? "Revision recommended"
                    : "No revision recommended"}
                </span>
                <p>{output.evaluation.assessment.summary}</p>
                <button
                  className="text-button"
                  onClick={() => setTab("feedback")}
                >
                  Explore the feedback →
                </button>
                <div className="sidebar-rule" />
                <p className="fine-print">
                  {output.revision_count
                    ? "One automatic revision completed."
                    : "No automatic revision was needed."}{" "}
                  {output.stop_reason === "revision_limit_reached"
                    ? "The revision limit was reached. Review the feedback or generate a new version."
                    : ""}
                </p>
                <p className="fine-print">
                  AI feedback is a guide, not an objective verdict.
                </p>
                {output.warnings.map((w) => (
                  <p key={w} className="fine-print">
                    {w}
                  </p>
                ))}
              </aside>
            </div>
          ) : (
            <div className="empty-state">
              <h2>No completed draft yet.</h2>
              <p>Generate a new version or check the run history.</p>
            </div>
          )
        ) : tab === "feedback" ? (
          output ? (
            <>
              <Feedback report={output.evaluation} />
              {output.revision_count > 0 ? (
                <details className="card-details">
                  <summary>
                    Compare the initial evaluation (
                    {output.initial_evaluation.overall_score.toFixed(1)}/10)
                  </summary>
                  <Feedback report={output.initial_evaluation} />
                  <h2>Original draft</h2>
                  <ScriptView script={output.initial_script} />
                </details>
              ) : null}
            </>
          ) : (
            <p>No evaluation is available for this run.</p>
          )
        ) : tab === "outline" ? (
          output ? (
            <article className="manuscript">
              <p className="eyebrow">THE STORY PLAN</p>
              <h2>{output.outline.title}</h2>
              <h3>Setting</h3>
              <p>{output.outline.setting}</p>
              <h3>Central conflict</h3>
              <p>{output.outline.conflict}</p>
              <h3>Characters</h3>
              {output.outline.characters.map((c) => (
                <div key={c.name}>
                  <h4>{c.name}</h4>
                  <p>{c.goal}</p>
                  <p className="muted">{c.traits}</p>
                </div>
              ))}
              <h3>Scene beats</h3>
              <ol>
                {output.outline.scene_beats.map((beat, i) => (
                  <li key={i}>{beat}</li>
                ))}
              </ol>
            </article>
          ) : (
            <p>No outline is available for this run.</p>
          )
        ) : tab === "edit" ? (
          <form className="manuscript edit-form" onSubmit={save}>
            <h2>Make it your own</h2>
            <p className="muted">
              These edits are saved separately from the AI drafts and scores.
              Editing always applies to the current story, even while viewing an
              older run.
            </p>
            <label htmlFor="story-title">Story title</label>
            <input
              id="story-title"
              value={title}
              required
              maxLength={300}
              onChange={(e) => setTitle(e.target.value)}
              disabled={busy}
            />
            <label htmlFor="story-text">Your manuscript</label>
            <textarea
              id="story-text"
              value={text}
              required
              minLength={1}
              maxLength={100000}
              rows={22}
              onChange={(e) => setText(e.target.value)}
              disabled={busy}
            />
            <button
              className="primary"
              disabled={busy || !title.trim() || !text.trim()}
            >
              Save my edits
            </button>
          </form>
        ) : (
          <div className="history-panel">
            <h2>Every version has a story</h2>
            <p className="muted">
              Open a run to review its draft and evaluation.
            </p>
            {historyError ? (
              <p className="error" role="alert">
                {historyError}
              </p>
            ) : historyLoading ? (
              <p role="status">Loading run history…</p>
            ) : (
              runs.map((r, index) => (
                <button
                  key={r.id}
                  className="history-row"
                  onClick={() => {
                    setHistorical(r);
                    setTab("story");
                  }}
                >
                  <span className="number-icon">
                    {historyPage * 10 + index + 1}
                  </span>
                  <div>
                    <strong>{new Date(r.started_at).toLocaleString()}</strong>
                    <small>
                      {r.output?.is_demo ? "Demo · " : ""}
                      {r.output
                        ? `${r.output.evaluation.overall_score.toFixed(1)}/10 · ${r.output.revision_count} automatic revisions`
                        : r.error_code || "Awaiting output"}
                    </small>
                  </div>
                  <span className="pill">{r.status}</span>
                  <span>↗</span>
                </button>
              ))
            )}
            <div className="pagination">
              <button
                className="secondary"
                disabled={historyPage === 0 || historyLoading}
                onClick={() => setHistoryPage((p) => p - 1)}
              >
                ← Previous
              </button>
              <span>Page {historyPage + 1}</span>
              <button
                className="secondary"
                disabled={runs.length < 10 || historyLoading || !!historyError}
                onClick={() => setHistoryPage((p) => p + 1)}
              >
                Next →
              </button>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

function ScriptView({ script }: { script: Script }) {
  return (
    <>
      <h2 className="script-title">{script.title}</h2>
      {script.scenes.map((scene, i) => (
        <section className="scene" key={i}>
          <p className="eyebrow">SCENE {i + 1}</p>
          <h3>{scene.heading}</h3>
          <p>{scene.narration}</p>
          {scene.dialogue.map((line, j) => (
            <p className="dialogue" key={j}>
              <strong>{line.speaker}</strong>
              {line.text}
            </p>
          ))}
        </section>
      ))}
    </>
  );
}
function Feedback({ report }: { report: Report }) {
  return (
    <section className="feedback">
      <div className="feedback-intro">
        <h2>
          {report.needs_revision
            ? "There’s room for another draft."
            : "A strong place to build from."}
        </h2>
        <p>{report.assessment.summary}</p>
        <p className="fine-print">
          Revision is recommended when the average is below 7 or any dimension
          is below 4. AI scores are subjective.
        </p>
      </div>
      <div className="rating-grid">
        {Object.entries(dimensions).map(([key, label]) => {
          const rating = report.assessment[key as keyof typeof dimensions];
          return (
            <article className="rating-card" key={key}>
              <div>
                <h3>{label}</h3>
                <b>
                  {rating.score}
                  <small>/10</small>
                </b>
              </div>
              <meter min={0} max={10} value={rating.score} aria-label={label} />
              <p>{rating.explanation}</p>
              <details>
                <summary>
                  Evidence · scenes {rating.scene_numbers.join(", ")}
                </summary>
                <blockquote>{rating.evidence}</blockquote>
              </details>
            </article>
          );
        })}
      </div>
      <div className="suggestions">
        <h2>Ideas for your next draft</h2>
        <ul>
          {report.assessment.revision_suggestions.map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ul>
      </div>
    </section>
  );
}
