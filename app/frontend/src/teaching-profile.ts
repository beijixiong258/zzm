import { t, dateLocale } from "./i18n";
import { api } from "./api";
import type {
  SessionDetail,
  SessionPatch,
  TeachingPhase,
  TeachingPreviewInput,
  TeachingProfile,
} from "./types";

export const teachingTextLimits = {
  background: 8000,
  student_profile: 8000,
  response_strategies: 8000,
  tone: 1000,
  reading_focus: 8000,
  instructions: 30000,
} as const;

export const teachingPhaseLabels: Record<TeachingPhase, string> = {
  warmup: "Welcome & review",
  worksheet: "Required worksheet",
  quiz: "Optional practice quiz",
  reading: "Reading discussion",
  wrap_up: "Wrap-up",
};

export function defaultTeachingProfile(
  kind: "new" | "legacy" = "new",
): TeachingProfile {
  return {
    schema_version: 1,
    background: "",
    student_profile: "",
    response_strategies: "",
    tone: "Supportive, specific and respectful; avoid excessive praise.",
    response_detail: "balanced",
    phases: ["warmup", "worksheet", "quiz", "wrap_up"],
    reading_focus: "",
    reading_question_count: 3,
    reference_delivery:
      kind === "legacy" ? "on_request" : "after_sufficient_answer",
    idle_hint_seconds: 0,
    presentation: "full",
  };
}

// Missing profiles are historical content, not an invitation to change reference rules.
export function effectiveTeachingProfile(
  session: Pick<SessionDetail, "teaching_profile">,
): TeachingProfile {
  return session.teaching_profile ?? defaultTeachingProfile("legacy");
}

export function teachingProfileErrors(p: TeachingProfile): string[] {
  const errors: string[] = [];
  if (p.schema_version !== 1)
    errors.push(t("Use teaching framework version 1."));
  for (const field of [
    "background",
    "student_profile",
    "response_strategies",
    "tone",
    "reading_focus",
  ] as const) {
    if (p[field].length > teachingTextLimits[field])
      errors.push(
        t("{0} exceeds {1} characters.", [
          t(
            {
              background: "Background",
              student_profile: "Student profile",
              response_strategies: "Response strategies",
              tone: "Tone",
              reading_focus: "Reading focus",
            }[field],
          ),
          teachingTextLimits[field].toLocaleString(dateLocale()),
        ]),
      );
  }
  const phases = p.phases;
  if (
    phases.some((phase) => !(phase in teachingPhaseLabels)) ||
    new Set(phases).size !== phases.length
  )
    errors.push(t("Use each teaching phase only once."));
  if (!phases.includes("worksheet") || phases.at(-1) !== "wrap_up")
    errors.push(t("Keep the required worksheet and a final wrap-up."));
  if (phases.includes("warmup") && phases[0] !== "warmup")
    errors.push(t("Welcome & review must be first."));
  if (
    ["quiz", "reading"].some(
      (phase) =>
        phases.includes(phase as TeachingPhase) &&
        phases.indexOf(phase as TeachingPhase) < phases.indexOf("worksheet"),
    )
  )
    errors.push(
      t("Practice quiz and reading discussion must follow the worksheet."),
    );
  if (
    !Number.isInteger(p.reading_question_count) ||
    p.reading_question_count < 1 ||
    p.reading_question_count > 5
  )
    errors.push(t("Reading discussion needs 1–5 questions."));
  if (
    !Number.isInteger(p.idle_hint_seconds) ||
    (p.idle_hint_seconds !== 0 &&
      (p.idle_hint_seconds < 10 || p.idle_hint_seconds > 300))
  )
    errors.push(
      t("Idle invitation must be disabled (0) or set to 10–300 seconds."),
    );
  return errors;
}

export function toggleTeachingPhase(
  phases: TeachingPhase[],
  phase: "warmup" | "quiz" | "reading",
): TeachingPhase[] {
  if (phases.includes(phase)) return phases.filter((item) => item !== phase);
  return phase === "warmup"
    ? [phase, ...phases]
    : [...phases.slice(0, -1), phase, "wrap_up"];
}

export function moveTeachingPhase(
  phases: TeachingPhase[],
  phase: TeachingPhase,
  direction: -1 | 1,
): TeachingPhase[] {
  const index = phases.indexOf(phase);
  const next = index + direction;
  const result = [...phases];
  if (index < 0 || next < 0 || next >= phases.length) return result;
  [result[index], result[next]] = [result[next], result[index]];
  return teachingProfileErrors({ ...defaultTeachingProfile(), phases: result })
    .length
    ? [...phases]
    : result;
}

export function teachingPreviewInput(
  session: SessionDetail,
): TeachingPreviewInput {
  return {
    teaching_profile: effectiveTeachingProfile(session),
    instructions: session.instructions,
    learning_objectives: session.learning_objectives,
    teaching_language: session.teaching_language,
    reference_policy: session.reference_policy,
  };
}

// Fixed field order makes freshness/read-back independent of JSON property order.
export function teachingProfileKey(p: TeachingProfile): string {
  return JSON.stringify([
    p.schema_version,
    p.background,
    p.student_profile,
    p.response_strategies,
    p.tone,
    p.response_detail,
    p.phases,
    p.reading_focus,
    p.reading_question_count,
    p.reference_delivery,
    p.idle_hint_seconds,
    p.presentation,
  ]);
}

export function teachingPreviewKey(session: SessionDetail): string {
  return JSON.stringify([
    session.id,
    teachingProfileKey(effectiveTeachingProfile(session)),
    session.instructions,
    session.learning_objectives,
    session.teaching_language,
    session.reference_policy,
  ]);
}

export async function saveTeachingDraft(
  sid: string,
  draft: SessionDetail,
): Promise<SessionDetail> {
  const profile = effectiveTeachingProfile(draft);
  const errors = teachingProfileErrors(profile);
  if (draft.instructions.length > teachingTextLimits.instructions)
    errors.push(t("Additional instructions exceed 30,000 characters."));
  if (errors.length) throw new Error(errors.join("; "));
  const payload: SessionPatch = {
    title: draft.title,
    subtitle: draft.subtitle,
    instructions: draft.instructions,
    learning_objectives: draft.learning_objectives,
    reference_policy: draft.reference_policy,
    teaching_language: draft.teaching_language,
    teaching_profile: profile,
    status: draft.status,
  };
  await api.updateSession(sid, payload);
  const verified = await api.session(sid);
  if (
    !verified.teaching_profile ||
    teachingPreviewKey(verified) !== teachingPreviewKey(draft)
  )
    throw new Error(
      t(
        "Teaching changes could not be verified after saving. Your local edits are still here; retry the save.",
      ),
    );
  return verified;
}
