import { lazy, Suspense } from "react";
import type { AiStatus, User, Course } from "./types";
import { Loading } from "./ui";
const Feedback = lazy(() => import("./Feedback"));
import Profile from "./Profile";
import ModelSettings from "./ModelSettings";
import SearchSettings from "./SearchSettings";
import AdminAccounts from "./AdminAccounts";
const CourseStudents = lazy(() => import("./CourseStudents"));
import {
  permittedSection,
  SETTINGS_SECTIONS,
  type SettingsSection,
} from "./stage7-settings";
import "./settings-workspace.css";
export type { SettingsSection } from "./stage7-settings";

export default function SettingsWorkspace({
  user,
  section = "account",
  onSection,
  onUserUpdate,
  onAiUpdate,
  courses = [],
  onAccountsChanged,
}: {
  user: User;
  section?: SettingsSection;
  onSection: (section: SettingsSection) => void;
  onUserUpdate: (user: User) => void;
  onAiUpdate: (ai: AiStatus) => void;
  courses?: Course[];
  onAccountsChanged?: () => void;
}) {
  const active = permittedSection(user, section);
  const sections =
    user.role === "admin"
      ? SETTINGS_SECTIONS
      : SETTINGS_SECTIONS.filter((s) => s.id === "account" || s.id === "feedback" || (user.role === "teacher" && s.id === "users"));
  return (
    <div className="page settings-workspace">
      <header className="settings-page-heading">
        <div className="eyebrow">YOUR WORKSPACE</div>
        <h1>Settings</h1>
      </header>
      <div className="settings-workspace-layout">
        <nav className="settings-local-nav" aria-label="Settings sections">
          {sections.map((s) => (
            <button
              key={s.id}
              type="button"
              aria-current={active === s.id ? "page" : undefined}
              className={active === s.id ? "selected" : ""}
              onClick={() => {
                if (s.id !== active) onSection(s.id);
              }}
            >
              {s.id === "users" && user.role === "teacher" ? "Course Students" : s.label}
            </button>
          ))}
        </nav>
        <div className="settings-content" key={`${user.id}:${user.role}:${active}`}>
          {active === "account" && (
            <Profile user={user} onUpdate={onUserUpdate} />
          )}
          {active === "feedback" && <Suspense fallback={<Loading />}><Feedback user={user} /></Suspense>}
          {user.role === "admin" && active === "model" && (
            <ModelSettings onUpdate={onAiUpdate} />
          )}
          {user.role === "admin" && active === "search" && <SearchSettings />}
          {user.role === "admin" && active === "users" && <AdminAccounts user={user} onChanged={onAccountsChanged} />}
          {user.role === "teacher" && active === "users" && <Suspense fallback={<Loading />}><CourseStudents user={user} courses={courses} onChanged={onAccountsChanged} /></Suspense>}
        </div>
      </div>
    </div>
  );
}
