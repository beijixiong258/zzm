import type { Workspace, Question } from "../src/types";
// Synthetic fixtures for isolated front-end tests only. Not loaded by the app.
const question = (id: string, group_id: string): Question => ({
  id,
  group_id,
  ordinal: 1,
  type: "open_response",
  prompt: "Explain this synthetic assessment concept.",
  options: [],
  answer_slots: 1,
  images: [],
  source_label: "Explicit test fixture",
});
export function fixtureWorkspace(): Workspace {
  return {
    session: {
      id: "test-session",
      course_id: "test-course",
      number: 2,
      title: "Explicit fixture session",
      subtitle: "Not live course data",
      status: "published",
      question_count: 3,
      estimated_minutes: 10,
      learning_objectives: ["Explain a synthetic concept."],
      instructions: "Test fixture only.",
      reference_policy: "after_attempt",
      teaching_language: "en",
      groups: [
        { id: "I", title: "Core", kind: "core" },
        { id: "II-Pong", title: "Pong reading", kind: "reading" },
        { id: "II-Bray", title: "Bray reading", kind: "reading" },
      ],
      questions: [
        question("core", "I"),
        question("pong", "II-Pong"),
        question("bray", "II-Bray"),
      ],
      materials: [],
    },
    user: {
      id: "fixture-user",
      name: "Fixture student",
      email: "fixture@example.invalid",
      role: "student",
    },
    selected_reading: "II-Pong",
    attempts: {},
    messages: [],
    progress: {
      answered: 0,
      total: 2,
      active_question_ids: ["core", "pong"],
      current_question_id: "core",
    },
    submission: {
      status: "not_started",
      submitted_at: null,
      reviewed_at: null,
      teacher_note: "",
    },
    ai: { mode: "demo", configured: true, base_url: "", model: "demo" },
  };
}
