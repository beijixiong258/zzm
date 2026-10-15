import { useCallback, useEffect, useState } from "react";
import { ArrowRight, Library, RefreshCw } from "lucide-react";
import { api } from "./api";
import type { CourseMaterial, SessionSummary } from "./types";
import { Empty, ErrorBanner, Loading, errorMessage } from "./ui";
import Materials from "./Materials";
import HelpPopover from "./HelpPopover";
import "./course-library.css";

export function filterCourseMaterials(
  materials: CourseMaterial[],
  query: string,
  visibility: string,
  sessionId: string,
) {
  const term = query.trim().toLocaleLowerCase();
  return materials.filter(
    (m) =>
      (!term ||
        `${m.title} ${m.source_label} ${m.kind}`
          .toLocaleLowerCase()
          .includes(term)) &&
      (!visibility || m.visibility === visibility) &&
      (!sessionId ||
        (sessionId === "unlinked"
          ? m.session_ids.length === 0
          : m.session_ids.includes(sessionId))),
  );
}

/** Owner-only canonical files and their draft session memberships. */
export default function CourseLibrary({
  courseId,
  onOpenSession,
}: {
  courseId: string;
  onOpenSession: (sid: string) => void;
}) {
  const [materials, setMaterials] = useState<CourseMaterial[]>([]);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [query, setQuery] = useState("");
  const [visibility, setVisibility] = useState("");
  const [sessionFilter, setSessionFilter] = useState("");
  const [manageSession, setManageSession] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const refresh = useCallback(() => setRetry((n) => n + 1), []);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    setQuery("");
    setVisibility("");
    setSessionFilter("");
    setManageSession("");
    Promise.all([api.courseMaterials(courseId), api.sessions(courseId)])
      .then(([library, list]) => {
        if (!active) return;
        setMaterials(library.materials);
        setSessions(list);
      })
      .catch((e) => {
        if (active) setError(errorMessage(e));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [courseId, retry]);
  const filtered = filterCourseMaterials(
    materials,
    query,
    visibility,
    sessionFilter,
  );
  const needsReview = materials.filter(
    (m) => m.status === "needs_review" || m.status === "error",
  ).length;
  return (
    <div className="page course-library">
      <header className="page-heading">
        <div>
          <div className="eyebrow">COURSE RESOURCES</div>
          <h1>Course materials</h1>
          <p>One course file, reusable across session drafts.</p>
        </div>
        <button className="secondary" disabled={loading} onClick={refresh}>
          <RefreshCw size={16} /> Refresh
        </button>
      </header>
      <ErrorBanner error={error} retry={refresh} />
      {loading ? (
        <Loading />
      ) : error ? null : (
        <>
          <section
            className="library-management card"
            aria-label="Manage course materials"
          >
            <div>
              <h2>
                <Library size={20} /> Add or manage materials
              </h2>
              <p>
                Choose a session to upload, add a link, or reuse a course file.
              </p>
              <small>
                Shared title, visibility and source edits apply to linked
                drafts. Published editions stay unchanged.
              </small>
            </div>
            <label>
              Session
              <select
                aria-label="Session"
                value={manageSession}
                onChange={(e) => setManageSession(e.target.value)}
              >
                <option value="">Choose a session</option>
                {sessions.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.number}. {s.title}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="primary"
              disabled={!sessions.some((s) => s.id === manageSession)}
              onClick={() => onOpenSession(manageSession)}
            >
              Manage in session <ArrowRight size={16} />
            </button>
            {!sessions.length && (
              <p className="library-empty-session">
                Create a session from Course Home before adding materials.
              </p>
            )}
          </section>
          <div className="library-summary" aria-live="polite">
            <span>
              {materials.length} course{" "}
              {materials.length === 1 ? "material" : "materials"}
            </span>
            <span>
              {materials.filter((m) => m.visibility === "teacher").length}{" "}
              teacher-only
            </span>
            {needsReview > 0 && (
              <span className="library-attention">
                ! {needsReview} need extraction review
              </span>
            )}
            <HelpPopover label="course material access">
              Teacher-only materials remain private. These are draft
              memberships, not evidence that a material is published to
              students.
            </HelpPopover>
          </div>
          <section
            className="library-filters"
            aria-label="Filter course materials"
          >
            <label>
              Find a material
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Title, source or type"
              />
            </label>
            <label>
              Visibility
              <select
                aria-label="Visibility"
                value={visibility}
                onChange={(e) => setVisibility(e.target.value)}
              >
                <option value="">All visibility</option>
                <option value="student">Student visible</option>
                <option value="teacher">Teacher only</option>
              </select>
            </label>
            <label>
              Linked session
              <select
                aria-label="Linked session"
                value={sessionFilter}
                onChange={(e) => setSessionFilter(e.target.value)}
              >
                <option value="">All memberships</option>
                <option value="unlinked">Not linked to a session</option>
                {sessions.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.number}. {s.title}
                  </option>
                ))}
              </select>
            </label>
          </section>
          <p className="library-result-count" role="status">
            Showing {filtered.length} of {materials.length}
          </p>
          <div className="library-list">
            {filtered.map((m) => (
              <section
                className="library-item"
                key={m.id}
                data-library-material={m.id}
              >
                <Materials materials={[m]} teacher />
                <div className="library-memberships">
                  <strong>Session drafts</strong>
                  {m.session_ids.length ? (
                    m.session_ids.map((id) => {
                      const session = sessions.find((s) => s.id === id);
                      return session ? (
                        <button
                          className="text-button"
                          key={id}
                          onClick={() => onOpenSession(id)}
                        >
                          {session.number}. {session.title}{" "}
                          <ArrowRight size={14} />
                        </button>
                      ) : (
                        <span key={id}>Linked session unavailable</span>
                      );
                    })
                  ) : (
                    <span>Not linked · retained in the course library</span>
                  )}
                </div>
              </section>
            ))}
          </div>
          {!filtered.length && (
            <Empty
              title={
                materials.length
                  ? "No matching materials"
                  : "No course materials yet"
              }
              description={
                materials.length
                  ? "Change the search or filters to see other files."
                  : "Open a session above to add the first file or link."
              }
            />
          )}
        </>
      )}
    </div>
  );
}
