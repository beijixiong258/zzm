import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  ArrowUpRight,
  ArrowRight,
  Plus,
  Clock,
  BookOpen,
  Layers,
  Users,
  Trash2,
  ShieldCheck,
  GraduationCap,
} from "lucide-react";
import type { Course, CourseDetails, User, SessionSummary } from "./types";
import { api } from "./api";
import { isStaff } from "./stage2";
import { AvailabilityBadge } from "./Availability";
import { useUiText } from "./uiText";
import { useUnsavedChanges } from "./navigation-guard";
import CourseActions from "./CourseActions";
import SessionActions, {DeletedSessions} from "./SessionActions";
import { populationLabel } from "./course-presentation";
import "./course-home.css";
import { Empty, Status, Loading, ErrorBanner, Notice, errorMessage } from "./ui";
export default function Home({
  user,
  courses,
  sessionMap,
  loading,
  history,
  onOpen,
  onPreview,
  onRefresh,
  onRoster,
  onVersions,
  onMaterials,
  onTrash,
  onCourseChanged,
  onActiveCourseChange,
}: {
  user: User;
  courses: Course[];
  sessionMap: Record<string, SessionSummary[]>;
  loading: boolean;
  history: boolean;
  onOpen: (sid: string) => void;
  onPreview: (sid: string) => void;
  onRefresh: () => Promise<void>;
  onRoster: (cid: string) => void;
  onVersions: (cid: string) => void;
  onMaterials?: (cid: string) => void;
  onTrash?: () => void;
  onCourseChanged?: (course: CourseDetails) => Promise<void>;
  onActiveCourseChange?: (courseId: string | undefined) => void;
}) {
  const { t } = useUiText();

  const [selected, setSelected] = useState("");
  const heading = useRef<HTMLHeadingElement>(null);
  const [notice,setNotice] = useState("");
  const course = courses.find((c) => c.id === selected) || courses[0];
  useEffect(() => { onActiveCourseChange?.(course?.id); }, [course?.id, onActiveCourseChange]);
  const [dialog, setDialog] = useState<"course" | "join" | "session" | null>(
    null,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    title: "",
    code: "",
    description: "",
    join_code: "",
    number: "1",
  });
  useUnsavedChanges(
    !!dialog &&
      (busy ||
        !!form.title ||
        !!form.code ||
        !!form.description ||
        !!form.join_code ||
        form.number !== "1"),
  );
  async function create(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (dialog === "course")
        await api.createCourse(form.title, form.code, form.description);
      if (dialog === "join") await api.joinCourse(form.join_code);
      if (dialog === "session" && course)
        await api.createSession(course.id, form.title, Number(form.number));
      await onRefresh();
      setDialog(null);
      setForm({
        title: "",
        code: "",
        description: "",
        join_code: "",
        number: "1",
      });
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  async function courseChanged(updated:CourseDetails) {
    if(onCourseChanged)await onCourseChanged(updated);else await onRefresh();
    setNotice(updated.trashed_at ? "Course moved to trash." : "Course draft saved.");
    if(updated.trashed_at){setSelected("");requestAnimationFrame(()=>heading.current?.focus());}
  }
  const sessions = course ? sessionMap[course.id] || [] : [];
  const all = Object.values(sessionMap).flat();
  return (
    <div className="page home-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow">{t("courseSpace")}</div>
          <h1 ref={heading} tabIndex={-1}>{history ? "My Learning" : "Course Home"}</h1>
          <p>
            {history
              ? t("historyIntro")
              : t(isStaff(user.role) ? "teacherIntro" : "homeIntro")}
          </p>
        </div>
        <div className="button-row">
        {isStaff(user.role)&&onTrash&&<button className="secondary" disabled={busy||!!dialog} onClick={onTrash}><Trash2 size={16}/>Trash</button>}
        <button
          className="secondary"
          disabled={busy||!!dialog}
          onClick={() => setDialog(isStaff(user.role) ? "course" : "join")}
        >
          <Plus size={16} />
          {t(isStaff(user.role) ? "createCourse" : "joinCourse")}
        </button>
        </div>
      </div>
      <ErrorBanner error={error} onClose={() => setError("")} />
      {notice&&<div role="status"><Notice>{notice}</Notice></div>}
      {dialog && (
        <div className="inline-form card">
          <h3>
            {t(
              dialog === "course"
                ? "createCourse"
                : dialog === "session"
                  ? "createSession"
                  : "joinCourse",
            )}
          </h3>
          <form onSubmit={create}>
            <div className="form-grid">
              {dialog === "join" ? (
                <label>
                  {t("joinCode")}
                  <input
                    required
                    value={form.join_code}
                    onChange={(e) =>
                      setForm({ ...form, join_code: e.target.value })
                    }
                  />
                </label>
              ) : (
                <>
                  <label>
                    {t("title")}
                    <input
                      required
                      value={form.title}
                      onChange={(e) =>
                        setForm({ ...form, title: e.target.value })
                      }
                    />
                  </label>
                  {dialog === "course" ? (
                    <label>
                      {t("code")}
                      <input
                        required
                        value={form.code}
                        onChange={(e) =>
                          setForm({ ...form, code: e.target.value })
                        }
                      />
                    </label>
                  ) : (
                    <label>
                      {t("number")}
                      <input
                        required
                        type="number"
                        min="1"
                        value={form.number}
                        onChange={(e) =>
                          setForm({ ...form, number: e.target.value })
                        }
                      />
                    </label>
                  )}
                </>
              )}
              {dialog === "course" && (
                <label className="span-two">
                  {t("description")}
                  <textarea
                    value={form.description}
                    onChange={(e) =>
                      setForm({ ...form, description: e.target.value })
                    }
                  />
                </label>
              )}
            </div>
            <div className="button-row">
              <button className="primary" disabled={busy}>
                {t("save")}
              </button>
              <button
                type="button"
                className="secondary"
                onClick={() => setDialog(null)}
              >
                {t("cancel")}
              </button>
            </div>
          </form>
        </div>
      )}
      {loading ? (
        <Loading />
      ) : !courses.length ? (
        <Empty
          title={t("noCourses")}
          description={t(isStaff(user.role) ? "emptyTeacher" : "emptyCourse")}
        />
      ) : history ? (
        <section className="history-list card">
          {all.map((s) => (
            <button
              key={s.id}
              className="history-row"
              onClick={() => onOpen(s.id)}
            >
              <span className="session-number large">
                {String(s.number).padStart(2, "0")}
              </span>
              <span className="history-title">
                <small>
                  {courses.find((c) => c.id === s.course_id)?.code} ·{" "}
                  {t("session")} {s.number}
                </small>
                <strong>{s.title}</strong>
                <span>{s.subtitle}</span>
              </span>
              <Status
                status={
                  isStaff(user.role)
                    ? s.status
                    : s.student_status || "not_started"
                }
              />
              <ArrowUpRight size={20} />
            </button>
          ))}
          {!all.length && <Empty title={t("noSessions")} />}
        </section>
      ) : (
        <>
          <div className="course-selector">
            {courses.map((c) => (
              <button
                key={c.id}
                className={course.id === c.id ? "active" : ""}
                disabled={busy||!!dialog}
                onClick={() => {setSelected(c.id);setNotice("");}}
              >
                {c.code}
                <span>{c.title}</span>
              </button>
            ))}
          </div>
          <section className="course-banner">
            <div className="course-banner-copy">
              <span className="course-code">{course.code}</span>
              <h2>{course.title}</h2>
              <p className="course-description">{course.description}</p>
              {isStaff(user.role) && course.join_code && (
                <div className="invitation">
                  {t("joinCode")}: <code>{course.join_code}</code>
                </div>
              )}
            </div>
            <div className="course-stats">
              <span>
                <Layers size={18} />
                <strong>{sessions.length}</strong>
                {populationLabel(sessions.length, "Session")}
              </span>
              <span>
                <ShieldCheck size={18} />
                <strong>{course.admin_count}</strong>
                {populationLabel(course.admin_count, "Admin")}
              </span>
              <span>
                <GraduationCap size={18} />
                <strong>{course.teacher_count}</strong>
                {populationLabel(course.teacher_count, "Teacher")}
              </span>
              <span>
                <Users size={18} />
                <strong>{course.student_count}</strong>
                {populationLabel(course.student_count, "Student")}
              </span>
            </div>
            <BookOpen className="banner-book" size={140} strokeWidth={0.7} />
          </section>
          {isStaff(user.role) && (
            <div className="course-management button-row">
              <CourseActions key={course.id} course={course} disabled={busy||!!dialog} onChanged={courseChanged}/>
              <button className="secondary" onClick={() => onRoster(course.id)}>
                {"Students"}
              </button>
              <button
                className="secondary"
                onClick={() => onVersions(course.id)}
              >
                {"Version history"}
              </button>
              {onMaterials && (
                <button
                  className="secondary"
                  onClick={() => onMaterials(course.id)}
                >
                  Course materials
                </button>
              )}
              <span>
                {course.published_version_number
                  ? `Published edition ${course.published_version_number}`
                  : "Not published yet"}
                {course.has_unpublished_changes &&
                  ` · ${"Unpublished changes"}`}
              </span>
            </div>
          )}
          <div className="section-heading">
            <h2>{t("sessions")}</h2>
            {isStaff(user.role) && (
              <button
                className="text-button"
                onClick={() => setDialog("session")}
              >
                <Plus size={15} />
                {t("createSession")}
              </button>
            )}
          </div>
          <div className="session-grid">
            {sessions.map((s) => (
              <article className="session-card card" key={s.id}>
                <div className="session-card-top">
                  <span className="session-number large">
                    {String(s.number).padStart(2, "0")}
                  </span>
                  <Status
                    status={
                      isStaff(user.role)
                        ? s.status
                        : s.student_status || "not_started"
                    }
                  />
                </div>
                <AvailabilityBadge session={s} />
                <div className="session-card-content">
                  <small>
                    {t("session")} {s.number}
                  </small>
                  <h3>{s.title}</h3>
                  <p>{s.subtitle}</p>
                  <div className="session-meta">
                    <span>
                      <Clock size={14} />
                      {s.estimated_minutes} {t("minutes")}
                    </span>
                    <span>
                      <Layers size={14} />
                      {s.question_count} {s.question_count === 1 ? "question" : t("questions")}
                    </span>
                  </div>
                  <div className="objectives-preview">
                    {s.learning_objectives.slice(0, 2).map((o, i) => (
                      <div key={i}>
                        <BookOpen size={14} />
                        <span>{o}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="session-card-footer">
                  <button className="primary" onClick={() => onOpen(s.id)}>
                    {isStaff(user.role)
                      ? "Teaching setup"
                      : s.student_status === "submitted" ||
                          s.student_status === "confirmed"
                        ? "Read your work"
                        : s.student_status === "in_progress" ||
                            s.student_status === "needs_revision"
                          ? "Continue learning"
                          : "Open session"}
                    <ArrowRight size={17} />
                  </button>
                  {isStaff(user.role) && (
                    <button
                      className="text-button"
                      title={t("preview")}
                      aria-label={t("preview")}
                      onClick={() => onPreview(s.id)}
                    >
                      Preview <ArrowUpRight size={16} />
                    </button>
                  )}
                </div>
                {isStaff(user.role) && <SessionActions session={s} onChanged={onRefresh} />}
              </article>
            ))}
          </div>
          {isStaff(user.role) && <DeletedSessions key={course.id} courseId={course.id} onChanged={onRefresh} />}
          {!sessions.length && <Empty title={t("noSessions")} />}
        </>
      )}
    </div>
  );
}
