import { useState } from "react";
import type { Course, User } from "./types";
import CourseStaff from "./CourseStaff";
import Roster from "./Roster";
import { confirmNavigation } from "./navigation-guard";
import "./account-management.css";
export default function CourseStudents(props: {
  user: User;
  courses: Course[];
  courseId?: string;
  onChanged?: () => void;
}) {
  return (
    <StudentCourses key={`${props.user.id}:${props.user.role}`} {...props} />
  );
}
function StudentCourses({
  user,
  courses,
  courseId,
  onChanged,
}: {
  user: User;
  courses: Course[];
  courseId?: string;
  onChanged?: () => void;
}) {
  const available = courses.filter((c) => !c.trashed_at),
    [selected, setSelected] = useState(available[0]?.id ?? ""),
    [staffHeld, setStaffHeld] = useState(false),
    [rosterHeld, setRosterHeld] = useState(false);
  if (user.role === "student")
    return (
      <p>Course student management is available only to assigned staff.</p>
    );
  const id = courseId ?? selected,
    course = available.find((c) => c.id === id);
  return (
    <div className="account-management">
      <h2>Course Students</h2>
      <p>
        Manage students only in your explicitly assigned courses. Removing a
        student affects this course enrollment and its retained learning
        records, not their global account or other enrollments.
      </p>
      {!courseId && (
        <label>
          Course for students
          <select
            aria-label="Course for students"
            value={course ? selected : ""}
            disabled={staffHeld || rosterHeld}
            onChange={(e) => {
              if (confirmNavigation()) setSelected(e.target.value);
            }}
          >
            <option value="">Choose an assigned course</option>
            {available.map((c) => (
              <option key={c.id} value={c.id}>
                {c.code} · {c.title}
              </option>
            ))}
          </select>
        </label>
      )}
      {!course ? (
        <p>
          No selected assigned course is available. Choose a course from your
          course index.
        </p>
      ) : (
        <div key={`${user.id}:${course.id}`}>
          <h3>
            {course.code} · {course.title}
          </h3>
          <CourseStaff
            user={user}
            courseId={course.id}
            onChanged={onChanged}
            onHold={setStaffHeld}
          />
          <Roster
            courseId={course.id}
            onChanged={onChanged}
            onHold={setRosterHeld}
          />
        </div>
      )}
    </div>
  );
}
