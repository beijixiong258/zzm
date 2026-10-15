import type { ReactNode } from "react";
import { ArrowDown, ArrowUp } from "lucide-react";
import type { SessionDetail, TeachingProfile } from "./types";
import {
  effectiveTeachingProfile,
  moveTeachingPhase,
  teachingPhaseLabels,
  teachingProfileErrors,
  teachingTextLimits,
  toggleTeachingPhase,
} from "./teaching-profile";
import HelpPopover from "./HelpPopover";
import "./teacher-framework.css";

export default function TeachingFramework({
  session,
  disabled = false,
  onChange,
  instructionImport,
}: {
  session: SessionDetail;
  disabled?: boolean;
  onChange: (patch: Partial<SessionDetail>) => void;
  instructionImport?: ReactNode;
}) {
  const profile = effectiveTeachingProfile(session);
  const errors = teachingProfileErrors(profile);
  if (session.instructions.length > teachingTextLimits.instructions)
    errors.push("Instructions exceed 30,000 characters.");
  function update(patch: Partial<TeachingProfile>) {
    onChange({ teaching_profile: { ...profile, ...patch } });
  }
  return (
    <section
      className="teaching-framework"
      aria-labelledby="teaching-framework-title"
    >
      <div className="tf-heading">
        <h2 id="teaching-framework-title">Teaching approach</h2>
        <HelpPopover label="Help with teaching approach">
          These private instructions guide the tutor. Questions and instructor
          answers stay in Questions &amp; answers. Save draft does not publish a
          course edition.
        </HelpPopover>
      </div>
      <fieldset className="tf-fields" disabled={disabled}>
        <legend className="tf-sr-only">Teaching approach settings</legend>
        <label className="tf-additional">
          Instructions
          <textarea
            aria-label="Instructions"
            rows={5}
            maxLength={teachingTextLimits.instructions}
            value={session.instructions}
            placeholder="Guide the tutor through this session."
            onChange={(e) => onChange({ instructions: e.target.value })}
          />
          <small>
            {session.instructions.length.toLocaleString("en-US")} / 30,000
            characters
          </small>
        </label>
        {instructionImport}
        <div className="tf-grid tf-feedback">
          <label className="tf-span-two">
            Feedback strategy
            <textarea
              rows={4}
              maxLength={teachingTextLimits.response_strategies}
              value={profile.response_strategies}
              placeholder="Start with a targeted hint, respond to the misconception, then invite a revision."
              onChange={(e) => update({ response_strategies: e.target.value })}
            />
          </label>
          <label>
            Tone
            <textarea
              rows={2}
              maxLength={teachingTextLimits.tone}
              value={profile.tone}
              onChange={(e) => update({ tone: e.target.value })}
            />
          </label>
          <label>
            Response detail
            <select
              value={profile.response_detail}
              onChange={(e) =>
                update({
                  response_detail: e.target
                    .value as TeachingProfile["response_detail"],
                })
              }
            >
              <option value="concise">Concise</option>
              <option value="balanced">Balanced</option>
              <option value="detailed">Detailed</option>
            </select>
          </label>
        </div>
        <section className="tf-block" aria-labelledby="tf-flow-title">
          <h3 id="tf-flow-title">Session flow</h3>
          <p>
            The worksheet is required. Practice and reading come afterwards;
            wrap-up is always last.
          </p>
          <div className="tf-phase-toggles">
            {(["warmup", "quiz", "reading"] as const).map((phase) => (
              <label key={phase} className="tf-check">
                <input
                  type="checkbox"
                  checked={profile.phases.includes(phase)}
                  onChange={() =>
                    update({
                      phases: toggleTeachingPhase(profile.phases, phase),
                    })
                  }
                />
                {teachingPhaseLabels[phase]}
              </label>
            ))}
          </div>
          <ol className="tf-flow-list" aria-label="Teaching phase order">
            {profile.phases.map((phase, index) => (
              <li key={phase}>
                <span className="tf-step" aria-hidden="true">
                  {index + 1}
                </span>
                <div className="tf-phase-name">
                  <strong>{teachingPhaseLabels[phase]}</strong>
                  <small>
                    {phase === "worksheet"
                      ? `${session.questions.length} configured question${session.questions.length === 1 ? "" : "s"} · required work`
                      : phase === "quiz"
                        ? "Five optional formative questions"
                        : phase === "reading"
                          ? `${profile.reading_question_count} discussion questions · grounded in student materials`
                          : phase === "warmup"
                            ? "Welcome and review before worksheet work"
                            : "Summarize learning · learner submits their own work"}
                  </small>
                </div>
                {phase === "quiz" || phase === "reading" ? (
                  <div className="tf-order-buttons">
                    {([-1, 1] as const).map((direction) => (
                      <button
                        type="button"
                        key={direction}
                        className="tf-icon-button"
                        aria-label={`Move ${teachingPhaseLabels[phase]} ${direction === -1 ? "earlier" : "later"}`}
                        disabled={
                          moveTeachingPhase(
                            profile.phases,
                            phase,
                            direction,
                          ).join() === profile.phases.join()
                        }
                        onClick={() =>
                          update({
                            phases: moveTeachingPhase(
                              profile.phases,
                              phase,
                              direction,
                            ),
                          })
                        }
                      >
                        {direction === -1 ? (
                          <ArrowUp size={16} aria-hidden="true" />
                        ) : (
                          <ArrowDown size={16} aria-hidden="true" />
                        )}
                      </button>
                    ))}
                  </div>
                ) : (
                  <span className="tf-required">
                    {phase === "warmup"
                      ? "First"
                      : phase === "wrap_up"
                        ? "Final"
                        : "Required"}
                  </span>
                )}
              </li>
            ))}
          </ol>
          {!session.questions.length && (
            <p className="tf-note">
              No worksheet questions yet. Add them in Questions & answers.
            </p>
          )}
          {profile.phases.includes("reading") && (
            <div className="tf-grid tf-reading">
              <label>
                Reading focus
                <textarea
                  rows={3}
                  maxLength={teachingTextLimits.reading_focus}
                  value={profile.reading_focus}
                  placeholder="Identify the ideas to discuss using the session's student-visible readings."
                  onChange={(e) => update({ reading_focus: e.target.value })}
                />
                <small>
                  Up to 8,000 characters. Add student-visible sources under
                  Materials.
                </small>
              </label>
              <label>
                Reading discussion questions
                <input
                  type="number"
                  min={1}
                  max={5}
                  step={1}
                  value={
                    Number.isFinite(profile.reading_question_count)
                      ? profile.reading_question_count
                      : ""
                  }
                  onChange={(e) =>
                    update({ reading_question_count: e.target.valueAsNumber })
                  }
                />
                <small>
                  A finite discussion of 1–5 questions, separate from worksheet
                  reading choices.
                </small>
              </label>
            </div>
          )}
        </section>

        <section className="tf-block" aria-labelledby="tf-examples-title">
          <div className="tf-heading">
            <h3 id="tf-examples-title">Instructor examples</h3>
            <HelpPopover label="Help with instructor examples">
              Eligibility is the earliest an instructor answer may be shown.
              Delivery controls how it is offered, never overriding eligibility
              or the learner's submission state.
            </HelpPopover>
          </div>
          {!session.teaching_profile && (
            <p className="tf-legacy">
              This existing session keeps examples on request.
            </p>
          )}
          <div className="tf-grid">
            <label>
              When examples become available
              <select
                value={session.reference_policy}
                onChange={(e) =>
                  onChange({
                    reference_policy: e.target
                      .value as SessionDetail["reference_policy"],
                  })
                }
              >
                <option value="after_attempt">After an attempt</option>
                <option value="after_feedback">After feedback</option>
                <option value="after_submit">After submission</option>
              </select>
            </label>
            <label>
              How examples are offered
              <select
                value={profile.reference_delivery}
                onChange={(e) =>
                  update({
                    reference_delivery: e.target
                      .value as TeachingProfile["reference_delivery"],
                  })
                }
              >
                <option value="after_sufficient_answer">
                  Offer comparison after a sufficient response
                </option>
                <option value="on_request">
                  Wait for the learner to request it
                </option>
              </select>
            </label>
          </div>
        </section>
        <details className="tf-details">
          <summary>Background &amp; learner context</summary>
          <div className="tf-grid">
            <label>
              Background &amp; tutor role
              <textarea
                rows={4}
                maxLength={teachingTextLimits.background}
                value={profile.background}
                onChange={(e) => update({ background: e.target.value })}
              />
              <small>Course context, not another list of objectives.</small>
            </label>
            <label>
              Student profile
              <textarea
                rows={4}
                maxLength={teachingTextLimits.student_profile}
                value={profile.student_profile}
                onChange={(e) => update({ student_profile: e.target.value })}
              />
              <small>
                Group-level needs only; avoid sensitive personal details.
              </small>
            </label>
          </div>
        </details>
        <details className="tf-details">
          <summary>Advanced delivery options</summary>
          <div className="tf-grid">
            <label>
              Response presentation
              <select
                value={profile.presentation}
                onChange={(e) =>
                  update({
                    presentation: e.target
                      .value as TeachingProfile["presentation"],
                  })
                }
              >
                <option value="full">Full response</option>
                <option value="paced">Paced reading</option>
              </select>
              <small>
                Paced reading reveals an already-generated response in parts.
              </small>
            </label>
            <label>
              Idle help invitation (seconds)
              <input
                type="number"
                min={0}
                max={300}
                step={1}
                value={
                  Number.isFinite(profile.idle_hint_seconds)
                    ? profile.idle_hint_seconds
                    : ""
                }
                onChange={(e) =>
                  update({ idle_hint_seconds: e.target.valueAsNumber })
                }
              />
              <small>
                0 = off; otherwise 10–300. An invitation, not an automatic AI
                request.
              </small>
            </label>
          </div>
        </details>
      </fieldset>
      {!!errors.length && (
        <div className="tf-validation" role="alert">
          <strong>Check teaching setup before saving.</strong>
          <ul>
            {errors.map((error) => (
              <li key={error}>{error}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
