import { useCallback, useEffect, useRef, useState, lazy, Suspense } from "react";
import {
  LayoutDashboard,
  History,
  Settings2,
  LogOut,
  ChevronRight,
  Menu,
  X,
  ArrowLeft,
} from "lucide-react";
import { api, ApiError } from "./api";
import type { Bootstrap, User, Course, CourseDetails, SessionSummary } from "./types";
import { uiText as t } from "./uiText";
import { Brand, Loading, ErrorBanner, errorMessage, AiBadge } from "./ui";
import Login from "./Login";
import Avatar from "./Avatar";
import Home from "./Home";
import LearningWorkspace from "./LearningWorkspace";
const TeacherSession = lazy(() => import("./TeacherSession"));
const SettingsWorkspace = lazy(() => import("./SettingsWorkspace"));
import ChangePassword from "./ChangePassword";
import { confirmNavigation } from "./navigation-guard";
const CourseStudents = lazy(() => import("./CourseStudents"));
const Versions = lazy(() => import("./Versions"));
const CourseLibrary = lazy(() => import("./CourseLibrary"));
const CourseTrash = lazy(() => import("./CourseTrash"));
const LearningHistory = lazy(() => import("./LearningHistory"));
import { isStaff } from "./stage2";
import { pageTitle } from "./course-presentation";
import { readRoute, routeHash, canAccessRoute, type Route } from "./routes";
import {LiveConnectionProvider} from "./live-connection";
export type { Route } from "./routes";
export default function App() {
  const [bootstrap, setBootstrap] = useState<Bootstrap | null>(null);
  const [aiRevision,setAiRevision] = useState(0);
  const [user, setUser] = useState<User | null>(null);
  const [booting, setBooting] = useState(true);
  const [error, setError] = useState("");
  const [route, setRoute] = useState<Route>(readRoute);
  const routeRef = useRef(route);
  const [mobile, setMobile] = useState(false);
  const [courses, setCourses] = useState<Course[]>([]);
  const [homeCourseId, setHomeCourseId] = useState<string | undefined>();
  const courseLoad = useRef(0);
  const userScope = useRef("");
  userScope.current = user ? `${user.id}:${user.role}:${!!user.must_change_password}` : "";
  const [sessionMap, setSessionMap] = useState<
    Record<string, SessionSummary[]>
  >({});
  const [coursesLoading, setCoursesLoading] = useState(false);

  const init = useCallback(async () => {
    setBooting(true);
    setError("");
    try {
      const boot = await api.bootstrap();
      setBootstrap(boot);
      try {
        setUser((await api.me()).user);
      } catch (e) {
        if (!(e instanceof ApiError && e.status === 401)) throw e;
        setUser(null);
      }
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBooting(false);
    }
  }, []);
  useEffect(() => {
    void init();
  }, [init]);
  const refreshCourses = useCallback(async () => {
    const generation = ++courseLoad.current, scope = userScope.current;
    const current = () => generation === courseLoad.current && scope === userScope.current;
    setCoursesLoading(true);
    try {
      const result = await api.courses();
      const maps = await Promise.all(
        result.map(async (c) => [c.id, await api.sessions(c.id)] as const),
      );
      if (!current()) return;
      setCourses(result);
      setSessionMap(Object.fromEntries(maps));
    } catch (e) {
      if (current()) setError(errorMessage(e));
    } finally {
      if (current()) setCoursesLoading(false);
    }
  }, []);
  useEffect(() => {
    if (user && !user.must_change_password) void refreshCourses();
    else {
      ++courseLoad.current;
      setCourses([]);
      setSessionMap({});
      setHomeCourseId(undefined);
      setCoursesLoading(false);
    }
  }, [user, refreshCourses]);
  useEffect(() => {
    const listener = () => {
      const next = readRoute();
      if (routeHash(next) !== routeHash(routeRef.current) && !confirmNavigation()) {
        history.replaceState(history.state, "", `#${routeHash(routeRef.current)}`);
        return;
      }
      routeRef.current = next;
      setRoute(next);
      setMobile(false);
    };
    window.addEventListener("hashchange", listener);
    return () => window.removeEventListener("hashchange", listener);
  }, []);
  useEffect(() => {
    // Ignore legacy UI locale preferences without clearing scoped learning drafts.
    document.documentElement.lang = "en";
  }, []);
  function commitRoute(value: Route) {
    routeRef.current = value;
    location.hash = routeHash(value);
    setRoute(value);
    setMobile(false);
  }
  function navigate(value: Route) {
    if (routeHash(value) !== routeHash(routeRef.current) && !confirmNavigation()) return;
    commitRoute(value);
  }
  async function logout() {
    if (!confirmNavigation()) return;
    try {
      await api.logout();
      try {
        await api.me();
        throw new Error("Sign-out was not confirmed by the server.");
      } catch (e) {
        if (!(e instanceof ApiError && e.status === 401)) throw e;
      }
      setUser(null);
      commitRoute({ page: "home" });
      setBootstrap(null);
      setBootstrap(await api.bootstrap());
    } catch (e) {
      setError(errorMessage(e));
    }
  }
  async function courseChanged(updated: CourseDetails) {
    // This is verified server readback, not a speculative optimistic mutation.
    setCourses(old => updated.trashed_at ? old.filter(c => c.id !== updated.id)
      : old.some(c => c.id === updated.id) ? old.map(c => c.id === updated.id ? updated : c) : [...old, updated]);
    if (updated.trashed_at) setSessionMap(old => {const next = {...old}; delete next[updated.id]; return next;});
    await refreshCourses();
  }
  const current = ["teacher", "workspace", "record"].includes(route.page)
    ? Object.values(sessionMap).flat().find((s) => s.id === route.sid)
    : undefined;
  const course = courses.find((c) => c.id === (current?.course_id ||
    (["roster", "versions", "course-materials"].includes(route.page) ? route.sid : undefined)));
  const title = pageTitle(user, route, courses.find(c => c.id === homeCourseId), course);
  useEffect(() => { document.title = title; }, [title]);
  const open = (sid: string) =>
    navigate({
      page: user && isStaff(user.role) ? "teacher" : "workspace",
      sid,
    });
  let content;
  if (booting) content = <Loading />;
  else if (!user)
    content = (
      <Login
        bootstrap={bootstrap}
        onAuthenticated={async () => {
          setUser((await api.me()).user);
          navigate({ page: "home" });
        }}
      />
    );
  else if (user.must_change_password)
    content = (
      <ChangePassword
        user={user}
        onLogout={logout}
        onComplete={(verified) => {
          setError("");
          setUser(verified);
          navigate({ page: "home" });
        }}
      />
    );
  else if (!canAccessRoute(user.role, route.page))
    content = (
      <div className="page">
        <ErrorBanner error="This page is not available to your role." />
      </div>
    );
  else if (route.page === "history")
    content = (
      <LearningHistory
        onOpen={(sid, version) => navigate({ page: "workspace", sid, version })}
      />
    );
  else if (["settings", "profile", "accounts"].includes(route.page))
    content = <SettingsWorkspace user={user}
      section={route.page === "profile" ? "account" : route.page === "accounts" ? "users" : route.section}
      onSection={(section) => navigate({page: "settings", section})}
      onUserUpdate={setUser}
      courses={courses}
      onAccountsChanged={() => void refreshCourses()}
      onAiUpdate={(ai) => {setBootstrap((b) => b ? {...b, ai} : b);setAiRevision(n=>n+1);}} />;
  else if (route.page === "course-trash" && isStaff(user.role))
    content = <CourseTrash onRestored={courseChanged} onBack={() => navigate({page:"home"})} />;
  else if (route.page === "course-materials" && route.sid && isStaff(user.role))
    content = <CourseLibrary key={`${user.id}:${route.sid}`} courseId={route.sid} onOpenSession={open} />;
  else if (route.page === "roster" && route.sid)
    content = (
      <div className="page">
        <CourseStudents
          key={`${user.id}:${user.role}:${route.sid}`}
          user={user}
          courses={courses}
          courseId={route.sid}
          onChanged={() => void refreshCourses()}
        />
      </div>
    );
  else if (route.page === "versions" && route.sid)
    content = (
      <div className="page">
        <Versions
          key={`${user.id}:${route.sid}`}
          courseId={route.sid}
          onChanged={() => void refreshCourses()}
          onOpen={(sid, version) =>
            navigate({ page: "workspace", sid, version })
          }
        />
      </div>
    );
  else if (route.page === "teacher" && route.sid && isStaff(user.role))
    content = (
      <TeacherSession
        key={`${user.id}:${route.sid}`}
        sid={route.sid}
        viewerId={user.id}
        onVersions={(cid) => navigate({page:"versions",sid:cid})}
        onPreview={(sid, version) =>
          navigate({ page: "workspace", sid: sid || route.sid, version })
        }
        onRecord={(uid, version) =>
          navigate({ page: "record", sid: route.sid, uid, version })
        }
        onSaved={() => void refreshCourses()}
      />
    );
  else if ((route.page === "workspace" || route.page === "record") && route.sid)
    content = (
      <LearningWorkspace
        key={`${user.id}-${route.sid}-${route.uid || "self"}-${route.version || "current"}`}
        sid={route.sid}
        versionId={route.version}
        viewerId={user.id}
        onVersion={(version) => navigate({ ...route, version })}
        studentId={route.page === "record" ? route.uid : undefined}
        preview={isStaff(user.role) && route.page === "workspace"}
        onBack={() =>
          navigate({
            page: isStaff(user.role) ? "teacher" : "home",
            sid: isStaff(user.role) ? route.sid : undefined,
          })
        }
        onChanged={() => void refreshCourses()}
      />
    );
  else
    content = (
      <Home
        user={user}
        courses={courses}
        sessionMap={sessionMap}
        loading={coursesLoading}
        history={false}
        onOpen={open}
        onPreview={(sid) => navigate({ page: "workspace", sid })}
        onRefresh={refreshCourses}
        onRoster={(cid) => navigate({ page: "roster", sid: cid })}
        onVersions={(cid) => navigate({ page: "versions", sid: cid })}
        onMaterials={(cid) => navigate({ page: "course-materials", sid: cid })}
        onTrash={() => navigate({page:"course-trash"})}
        onCourseChanged={courseChanged}
        onActiveCourseChange={setHomeCourseId}
      />
    );
  return (
    <LiveConnectionProvider identity={user&&!user.must_change_password?`${user.id}:${user.role}`:null} refreshKey={JSON.stringify([bootstrap?.ai.mode,bootstrap?.ai.model,aiRevision])}>
      {!user || user.must_change_password ? (
        <div className="public-shell">
          {user?.must_change_password && <header className="public-header">
            <Brand onNavigateHome={() => navigate({ page: "home" })} />
          </header>}
          {error && (
            <div className="public-error">
              <ErrorBanner error={error} retry={init} />
            </div>
          )}
          <Suspense fallback={<Loading />}>{content}</Suspense>
        </div>
      ) : (
        <div className="app-shell">
          <button
            className="mobile-menu icon-button"
            aria-label={t("navigation")}
            onClick={() => setMobile(!mobile)}
          >
            {mobile ? <X /> : <Menu />}
          </button>
          {mobile && (
            <div className="nav-scrim" onClick={() => setMobile(false)} />
          )}
          <aside className={`sidebar ${mobile ? "mobile-open" : ""}`}>
            <Brand appearance="panel" onNavigateHome={() => navigate({ page: "home" })} />
            <div className="sidebar-label">
              {isStaff(user.role) ? "TEACHING SPACE" : t("workspaceLabel")}
            </div>
            <nav className="main-nav">
              <button
                className={["home","course-trash"].includes(route.page) ? "active" : ""}
                onClick={() => navigate({ page: "home" })}
              >
                <LayoutDashboard size={18} />
                {t("home")}
              </button>
              <button
                className={route.page === "history" ? "active" : ""}
                onClick={() => navigate({ page: "history" })}
              >
                <History size={18} />
                {t("history")}
              </button>
              <button
                className={["settings", "profile", "accounts"].includes(route.page) ? "active" : ""}
                onClick={() => navigate({ page: "settings" })}
              >
                <Settings2 size={18} />
                {t("settings")}
              </button>
            </nav>
            {course && (
              <div className="course-nav">
                <div className="sidebar-label">{course.code}</div>
                <div className="sidebar-course-title">{course.title}</div>
                {isStaff(user.role) && <div className="course-management-links">
                  <button className={route.page === "course-materials" ? "active" : ""} onClick={() => navigate({page:"course-materials",sid:course.id})}>Course materials</button>
                  <button className={route.page === "roster" ? "active" : ""} onClick={() => navigate({page:"roster",sid:course.id})}>Students</button>
                  <button className={route.page === "versions" ? "active" : ""} onClick={() => navigate({page:"versions",sid:course.id})}>Publish & versions</button>
                </div>}
                {(sessionMap[course.id] || []).map((s) => (
                  <button
                    key={s.id}
                    className={`session-nav-item ${route.sid === s.id ? "active" : ""}`}
                    onClick={() => open(s.id)}
                  >
                    <span className="session-number">
                      {String(s.number).padStart(2, "0")}
                    </span>
                    <span>{s.title}</span>
                    <ChevronRight size={13} />
                  </button>
                ))}
              </div>
            )}
            <div className="sidebar-bottom">
              {bootstrap && <AiBadge ai={bootstrap.ai} detail />}

              <div className="user-card">
                <button
                  className="profile-entry"
                  aria-label={t("profile")}
                  title={t("profile")}
                  onClick={() => navigate({ page: "settings", section: "account" })}
                >
                  <Avatar user={user} />
                  <span>
                    <strong>{user.name}</strong>
                    <small>
                      {t(user.role)} · {t("profile")}
                    </small>
                  </span>
                </button>
                <button
                  className="icon-button"
                  title={t("logout")}
                  aria-label={t("logout")}
                  onClick={() => void logout()}
                >
                  <LogOut size={17} />
                </button>
              </div>
            </div>
          </aside>
          <main className="main-content">
            <header className="topbar">
              <div className="breadcrumb">
                <a href="#/home" onClick={(e) => { if (!e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey) {e.preventDefault();navigate({page:"home"});} }}>Course Home</a>
                {route.page !== "home" && <><ChevronRight size={13} />
                <span>{course?.code || (["settings","profile","accounts"].includes(route.page) ? "Settings" : route.page === "course-trash" ? "Course trash" : "My Learning")}</span></>}
                {current && (
                  <>
                    <ChevronRight size={13} />
                    <strong>
                      {t("session")} {current.number}
                    </strong>
                  </>
                )}
              </div>
              <div className="topbar-right">
                {route.sid && (
                  <button
                    className="text-button"
                    onClick={() => navigate({ page: "home" })}
                  >
                    <ArrowLeft size={14} />
                    {t("home")}
                  </button>
                )}
                <span className="role-pill">{t(user.role)}</span>
              </div>
            </header>
            {error && (
              <ErrorBanner error={error} onClose={() => setError("")} />
            )}
            <Suspense fallback={<Loading />}>{content}</Suspense>
          </main>
        </div>
      )}
    </LiveConnectionProvider>
  );
}
