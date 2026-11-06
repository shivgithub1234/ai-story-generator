"use client";

import {
  ClerkProvider,
  SignIn,
  SignUp,
  UserButton,
  useAuth,
  useUser,
} from "@clerk/react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Story, StoryInput, StorySummary } from "@/lib/types";
import StoryReader from "./story-reader";

const prompts = [
  {
    label: "A little magic",
    genre: "fantasy",
    text: "A mapmaker discovers that every island she draws appears in the ocean the following morning.",
  },
  {
    label: "An unsolved mystery",
    genre: "mystery",
    text: "Every night, a retired detective receives a postcard describing a crime that has not happened yet.",
  },
  {
    label: "Somewhere in space",
    genre: "science-fiction",
    text: "The last gardener on a space station finds a flower growing in a room that has been sealed for thirty years.",
  },
];
export const dateLabel = (value: string) =>
  new Date(value).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });

export default function Studio({ signUp = false }: { signUp?: boolean }) {
  const key = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
  if (!key)
    return (
      <main className="loading-page">
        <span className="brand">✳ Story Studio</span>
        <h1>Let’s open your studio.</h1>
        <p>
          Add your Clerk publishable key to frontend/.env.local and restart the
          frontend.
        </p>
      </main>
    );
  return (
    <ClerkProvider
      publishableKey={key}
      afterSignOutUrl="/"
      signInFallbackRedirectUrl="/"
      signUpFallbackRedirectUrl="/"
      signInUrl="/"
      signUpUrl="/sign-up"
    >
      <SessionGate signUp={signUp} />
    </ClerkProvider>
  );
}

function SessionGate({ signUp }: { signUp: boolean }) {
  const { isLoaded, isSignedIn, userId, sessionId } = useAuth();
  if (!isLoaded)
    return (
      <main className="loading-page">
        <span className="brand">✳ Story Studio</span>
        <p role="status">Connecting to your account…</p>
      </main>
    );
  if (!isSignedIn)
    return (
      <main className="welcome">
        <section className="welcome-copy">
          <a href="/" className="brand">
            ✳ Story Studio
          </a>
          <div>
            <p className="eyebrow">A SPACE FOR YOUR IMAGINATION</p>
            <h1>
              A little idea.
              <br />A whole
              <br />
              <em>new world.</em>
            </h1>
            <p>
              Turn the story in your head into the story on the page. Write with
              AI, explore thoughtful feedback, and make every draft your own.
            </p>
            <div className="welcome-steps">
              <span>01 &nbsp; Imagine</span>
              <span>02 &nbsp; Write</span>
              <span>03 &nbsp; Refine</span>
            </div>
          </div>
          <p className="fine-print">
            Your stories. Your space. Your next chapter.
          </p>
        </section>
        <section className="signin-panel" aria-label="Sign in">
          {signUp ? (
            <SignUp routing="hash" signInUrl="/" />
          ) : (
            <SignIn routing="hash" signUpUrl="/sign-up" />
          )}
          <p className="fine-print">Sign in to keep your stories together.</p>
        </section>
      </main>
    );
  return <Workspace key={`${userId}:${sessionId}`} />;
}

function Workspace() {
  const { getToken } = useAuth();
  const { user } = useUser();
  const [stories, setStories] = useState<StorySummary[]>([]);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [libraryError, setLibraryError] = useState("");
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<Story | null>(null);
  const [opening, setOpening] = useState(false);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [view, setView] = useState<"new" | "library" | "story">("new");
  const [premise, setPremise] = useState("");
  const [genre, setGenre] = useState("fantasy");
  const [language, setLanguage] = useState("English");
  const [words, setWords] = useState(1000);
  const [tone, setTone] = useState("");
  const openRequest = useRef(0);
  const request = useCallback(
    async <T,>(path: string, options?: RequestInit) =>
      api<T>(path, await getToken(), options),
    [getToken],
  );

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setLibraryError("");
    request<StorySummary[]>(`stories?limit=12&offset=${page * 12}`, {
      signal: controller.signal,
    })
      .then((data) => {
        if (!controller.signal.aborted) setStories(data);
      })
      .catch((err) => {
        if (!controller.signal.aborted)
          setLibraryError(
            err instanceof Error ? err.message : "Could not load your library.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [request, page, refresh]);

  useEffect(() => {
    if (!busy) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [busy]);

  async function open(id: string) {
    if (
      dirty &&
      !window.confirm(
        "Leave this story and discard your unsaved editor changes?",
      )
    )
      return;
    const sequence = ++openRequest.current;
    setOpening(true);
    setError("");
    setView("story");
    setSelected(null);
    try {
      const story = await request<Story>(`stories/${id}`);
      if (sequence === openRequest.current) setSelected(story);
    } catch (err) {
      if (sequence === openRequest.current)
        setError(err instanceof Error ? err.message : "Could not open story.");
    } finally {
      if (sequence === openRequest.current) setOpening(false);
    }
  }

  async function generate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    const body: StoryInput = {
      premise: premise.trim(),
      genre,
      language,
      target_words: words,
      tone: tone.trim() || null,
    };
    try {
      const story = await request<Story>("stories", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setSelected(story);
      setView("story");
      setPage(0);
      setRefresh((v) => v + 1);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not generate your story.",
      );
      setRefresh((v) => v + 1);
      if (err instanceof ApiError && err.storyId) {
        try {
          setSelected(await request<Story>(`stories/${err.storyId}`));
          setView("story");
        } catch {
          /* Keep original error. */
        }
      }
    } finally {
      setBusy(false);
    }
  }

  function navigate(next: "new" | "library") {
    if (
      dirty &&
      !window.confirm(
        "Leave this story and discard your unsaved editor changes?",
      )
    )
      return;
    ++openRequest.current;
    setOpening(false);
    setError("");
    setView(next);
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a href="/" className="brand">
          ✳ <span>Story Studio</span>
        </a>
        <p className="sidebar-caption">A place for your next chapter</p>
        <button
          className="primary new-button"
          disabled={busy}
          onClick={() => navigate("new")}
        >
          <span>＋</span> New story
        </button>
        <nav aria-label="Workspace">
          <button
            className={view === "library" ? "nav-item active" : "nav-item"}
            disabled={busy}
            onClick={() => navigate("library")}
          >
            <span>▤</span> My library <span className="nav-arrow">↗</span>
          </button>
        </nav>
        <div className="sidebar-rule" />
        <p className="eyebrow">YOUR RECENT STORIES</p>
        <div className="recent-list">
          {loading ? (
            <p className="muted" role="status">
              Loading your stories…
            </p>
          ) : libraryError ? (
            <p className="muted">
              Library unavailable. Open My library to retry.
            </p>
          ) : stories.length ? (
            stories.slice(0, 5).map((story) => (
              <button
                key={story.id}
                disabled={busy}
                className={
                  selected?.id === story.id && view === "story"
                    ? "recent active"
                    : "recent"
                }
                onClick={() => open(story.id)}
              >
                <span>{story.title}</span>
                <small>{dateLabel(story.created_at)}</small>
              </button>
            ))
          ) : (
            <p className="muted">
              The beginning of something good.
              <br />
              Your first story will appear here.
            </p>
          )}
        </div>
        <div className="sidebar-bottom">
          <div className="note">
            <span>“</span>
            <p>
              You don’t have to see the whole story to write the first line.
            </p>
          </div>
          <div className="profile">
            <UserButton />
            <div>
              <strong>{user?.firstName || "Your studio"}</strong>
              <small>Personal workspace</small>
            </div>
            <span className="online-dot" />
          </div>
        </div>
      </aside>
      <main className="main-content">
        <header className="topbar">
          <span>
            YOUR WORKSPACE <span className="crumb">/</span>{" "}
            <strong>
              {view === "new"
                ? "New story"
                : view === "library"
                  ? "My library"
                  : "Story desk"}
            </strong>
          </span>
          <span className="private-label">◈ &nbsp; Private to you</span>
        </header>
        <div className="content-wrap">
          {error ? (
            <div className="error" role="alert">
              {error}
              <button className="text-button" onClick={() => setError("")}>
                Dismiss
              </button>
            </div>
          ) : null}
          {view === "new" ? (
            <>
              <div className="page-heading">
                <p className="eyebrow">THE BLANK PAGE IS JUST THE BEGINNING</p>
                <h1>
                  What’s your <em>next story?</em>
                </h1>
                <p>
                  A spark of an idea is all you need. Let’s see where it takes
                  you.
                </p>
              </div>
              <div className="creation-grid">
                <form className="brief-card" onSubmit={generate}>
                  <div className="card-heading">
                    <span className="number-icon">01</span>
                    <div>
                      <h2>Start with a spark</h2>
                      <p>Set the scene. We’ll help you find the story.</p>
                    </div>
                    <span className="small-star">✳</span>
                  </div>
                  <label htmlFor="premise">Your story idea</label>
                  <textarea
                    id="premise"
                    required
                    minLength={10}
                    maxLength={2000}
                    rows={5}
                    placeholder="What if a mapmaker discovered that every island she drew became real?"
                    value={premise}
                    onChange={(e) => setPremise(e.target.value)}
                    disabled={busy}
                  />
                  <div className="field-meta">
                    <span>A character, a place, a curious “what if…”</span>
                    <span>{premise.length}/2,000</span>
                  </div>
                  <div className="field-grid">
                    <div>
                      <label htmlFor="genre">Genre</label>
                      <select
                        id="genre"
                        value={genre}
                        onChange={(e) => setGenre(e.target.value)}
                        disabled={busy}
                      >
                        {[
                          "fantasy",
                          "mystery",
                          "science-fiction",
                          "drama",
                          "comedy",
                          "horror",
                        ].map((g) => (
                          <option value={g} key={g}>
                            {g
                              .replace("-", " ")
                              .replace(/^./, (c) => c.toUpperCase())}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label htmlFor="language">Language</label>
                      <select
                        id="language"
                        value={language}
                        onChange={(e) => setLanguage(e.target.value)}
                        disabled={busy}
                      >
                        <option>English</option>
                        <option>Hindi</option>
                      </select>
                    </div>
                    <div>
                      <label htmlFor="words">Target word count</label>
                      <input
                        id="words"
                        type="number"
                        required
                        min={200}
                        max={3000}
                        step={1}
                        value={words}
                        onChange={(e) => setWords(Number(e.target.value))}
                        disabled={busy}
                      />
                    </div>
                    <div>
                      <label htmlFor="tone">
                        Tone <span className="optional">optional</span>
                      </label>
                      <input
                        id="tone"
                        placeholder="e.g. whimsical, suspenseful"
                        maxLength={100}
                        value={tone}
                        onChange={(e) => setTone(e.target.value)}
                        disabled={busy}
                      />
                    </div>
                  </div>
                  <div className="generate-footer">
                    <span>
                      ✧ &nbsp; A draft, an evaluation, a fresh perspective.
                    </span>
                    <button
                      className="primary"
                      disabled={busy || premise.trim().length < 10}
                      type="submit"
                    >
                      {busy ? "Writing your story…" : "Create my story"}
                      <span aria-hidden="true">↗</span>
                    </button>
                  </div>
                  {busy ? (
                    <div className="progress-panel" role="status">
                      <span className="spinner" /> Planning, writing, and
                      evaluating your story. This can take a few minutes; keep
                      this page open.
                    </div>
                  ) : null}
                </form>
                <aside className="how-card">
                  <span className="orbit-art" aria-hidden="true">
                    ✳
                  </span>
                  <p className="eyebrow">YOUR CREATIVE COMPANION</p>
                  <h2>
                    A little structure.
                    <br />
                    Room for wonder.
                  </h2>
                  <ol>
                    <li>
                      <span>01</span>
                      <div>
                        <strong>A thoughtful plan</strong>
                        <p>
                          Characters, setting, and a direction worth exploring.
                        </p>
                      </div>
                    </li>
                    <li>
                      <span>02</span>
                      <div>
                        <strong>A story takes shape</strong>
                        <p>
                          Your idea becomes scenes, dialogue, and a complete
                          draft.
                        </p>
                      </div>
                    </li>
                    <li>
                      <span>03</span>
                      <div>
                        <strong>A second pair of eyes</strong>
                        <p>
                          Five quality checks, clear feedback, and a revision
                          when needed.
                        </p>
                      </div>
                    </li>
                  </ol>
                  <p className="how-footnote">Made with AI. Shaped by you.</p>
                </aside>
              </div>
              <section className="inspiration">
                <div>
                  <h2>Need a starting point?</h2>
                  <span>Borrow a spark. Make it yours.</span>
                </div>
                <div className="prompt-grid">
                  {prompts.map((prompt, index) => (
                    <button
                      key={prompt.label}
                      disabled={busy}
                      onClick={() => {
                        setPremise(prompt.text);
                        setGenre(prompt.genre);
                        document.getElementById("premise")?.focus();
                      }}
                    >
                      <span className="prompt-icon">
                        {["✦", "◉", "☾"][index]}
                      </span>
                      <strong>{prompt.label}</strong>
                      <p>{prompt.text}</p>
                      <span className="prompt-arrow" aria-hidden="true">
                        ↗
                      </span>
                    </button>
                  ))}
                </div>
              </section>
            </>
          ) : view === "library" ? (
            <>
              <div className="page-heading">
                <p className="eyebrow">IDEAS YOU’VE BROUGHT TO LIFE</p>
                <h1>
                  Your story <em>library.</em>
                </h1>
                <p>Pick up where you left off. Every draft has a place here.</p>
              </div>
              <div className="library-toolbar">
                <h2>Saved stories</h2>
                <button
                  className="secondary"
                  onClick={() => setRefresh((v) => v + 1)}
                  disabled={loading}
                >
                  Refresh library
                </button>
              </div>
              {libraryError ? (
                <div className="error" role="alert">
                  {libraryError}
                </div>
              ) : loading ? (
                <p role="status">Opening your library…</p>
              ) : stories.length === 0 ? (
                <div className="empty-state">
                  <span>✳</span>
                  <h2>
                    {page
                      ? "You’ve reached the end."
                      : "Your first chapter starts here."}
                  </h2>
                  <p>
                    Create a story and it will be saved in your personal
                    library.
                  </p>
                  <button className="primary" onClick={() => navigate("new")}>
                    Write a story ↗
                  </button>
                </div>
              ) : (
                <div className="library-grid">
                  {stories.map((story, index) => (
                    <button
                      className="story-card"
                      key={story.id}
                      onClick={() => open(story.id)}
                    >
                      <div className={`book-cover cover-${index % 3}`}>
                        <span>STORY STUDIO</span>
                        <b>{["✳", "◐", "✧"][index % 3]}</b>
                        <span>YOUR ORIGINAL STORY</span>
                      </div>
                      <div className="story-card-text">
                        <small>{dateLabel(story.created_at)}</small>
                        <h2>{story.title}</h2>
                        <span>
                          Open story <b>↗</b>
                        </span>
                      </div>
                    </button>
                  ))}
                </div>
              )}
              <div className="pagination">
                <button
                  className="secondary"
                  disabled={page === 0 || loading}
                  onClick={() => setPage((p) => p - 1)}
                >
                  ← Previous
                </button>
                <span>Page {page + 1}</span>
                <button
                  className="secondary"
                  disabled={stories.length < 12 || loading || !!libraryError}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next →
                </button>
              </div>
            </>
          ) : opening ? (
            <p className="loading-page" role="status">
              Opening your story…
            </p>
          ) : selected ? (
            <StoryReader
              key={selected.id}
              story={selected}
              request={request}
              busy={busy}
              setBusy={setBusy}
              onDirtyChange={setDirty}
              onChange={(story) => {
                setSelected(story);
                setRefresh((v) => v + 1);
              }}
            />
          ) : (
            <div className="empty-state">
              <h2>Story unavailable</h2>
              <button className="secondary" onClick={() => navigate("library")}>
                Return to library
              </button>
            </div>
          )}
          <footer className="workspace-footer">
            <span>Story Studio</span>
            <span>A space for stories only you could imagine.</span>
          </footer>
        </div>
      </main>
    </div>
  );
}
