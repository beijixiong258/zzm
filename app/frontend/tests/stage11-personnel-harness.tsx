import { useState } from "react";
import { createRoot } from "react-dom/client";
import AdminAccounts from "../src/AdminAccounts";
import CourseStudents from "../src/CourseStudents";
import type { Course, User } from "../src/types";
import { confirmNavigation, hasUnsavedChanges } from "../src/navigation-guard";
import "../src/design-tokens.css";
import "../src/styles.css";
import "../src/contrast.css";
import "../src/stage2.css";
import "../src/settings-workspace.css";
const admin: User = {
  id: "admin",
  name: "Synthetic Admin",
  email: "admin@example.invalid",
  role: "admin",
};
const teacher: User = {
  id: "teacher-a",
  name: "Synthetic Teacher A",
  email: "teacher-a@example.invalid",
  role: "teacher",
};
const courses: Course[] = [
  {
    id: "c1",
    code: "SYN101",
    title: "Synthetic Course One",
    description: "Synthetic fixture only",
    admin_count: 1,
    teacher_count: 2,
    student_count: 1,
  },
  {
    id: "c2",
    code: "SYN202",
    title: "Synthetic Course Two",
    description: "Synthetic fixture only",
    admin_count: 1,
    teacher_count: 1,
    student_count: 1,
  },
];
function Harness() {
  const [mode, setMode] = useState("admin"),
    [account, setAccount] = useState(admin),
    [forcedCourse, setForcedCourse] = useState<string | undefined>();
  (window as unknown as { stage11Dirty: () => boolean }).stage11Dirty =
    hasUnsavedChanges;
  return (
    <main className="page" style={{ maxWidth: 1320, margin: "auto" }}>
      <header>
        <h1>Stage11 synthetic personnel fixture</h1>
        <p>
          Actual Chrome / synthetic HTTP responses. Not backend authorization or
          SQLite evidence.
        </p>
        <div className="button-row">
          <button
            className="secondary"
            onClick={() => {
              if (confirmNavigation()) {
                setMode("admin");
                setAccount(admin);
              }
            }}
          >
            Admin fixture
          </button>
          <button
            className="secondary"
            onClick={() => {
              if (confirmNavigation()) {
                setMode("teacher");
                setAccount(teacher);
              }
            }}
          >
            Teacher fixture
          </button>
          <button
            className="secondary"
            onClick={() => {
              setMode("teacher");
              setAccount(teacher);
            }}
          >
            Force account remount fixture
          </button>
          <button
            className="secondary"
            onClick={() => setForcedCourse(forcedCourse === "c2" ? "c1" : "c2")}
          >
            Force course remount fixture
          </button>
        </div>
      </header>
      {mode === "admin" ? (
        <AdminAccounts user={account} />
      ) : (
        <CourseStudents
          user={account}
          courses={courses}
          courseId={forcedCourse}
        />
      )}
    </main>
  );
}
createRoot(document.getElementById("root")!).render(<Harness />);
