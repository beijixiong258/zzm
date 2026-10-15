import { useState, type ReactNode } from "react";
import type { WorksheetDraft, Material, Question, Group } from "./types";
import { useUiText } from "./uiText";
import { moveItem, renumber, authoringErrors } from "./stage2";
import { clientId } from "./ids";
import HelpPopover from "./HelpPopover";
export const newGroup = (): Group => ({
  id: `g-${clientId()}`,
  title: "",
  kind: "core",
  description: "",
});
export const newQuestion = (gid: string, ordinal: number): Question => ({
  id: `q-${clientId()}`,
  group_id: gid,
  ordinal,
  type: "open_response",
  prompt: "",
  options: [],
  answer_slots: 1,
  images: [],
  source_label: "",
  source_material_ids: [],
  source_links: [],
});
export default function Authoring({
  value,
  onChange,
  materials,
  disabled = false,
}: {
  value: WorksheetDraft;
  onChange: (d: WorksheetDraft) => void;
  materials: Material[];
  disabled?: boolean;
}) {
  const { t } = useUiText();
  const [remove, setRemove] = useState<{
    kind: "group" | "question";
    id: string;
  } | null>(null);
  const update = (patch: Partial<WorksheetDraft>) =>
    onChange({ ...value, ...patch });
  const qpatch = (id: string, p: Partial<Question>) =>
    update({
      questions: value.questions.map((q) => (q.id === id ? { ...q, ...p } : q)),
    });
  const gpatch = (id: string, p: Partial<Group>) =>
    update({
      groups: value.groups.map((g) => (g.id === id ? { ...g, ...p } : g)),
    });
  function addQuestion() {
    let groups = value.groups;
    let gid = groups[0]?.id;
    if (!gid) {
      const g = newGroup();
      groups = [g];
      gid = g.id;
    }
    update({
      groups,
      questions: [
        ...value.questions,
        newQuestion(gid, value.questions.length + 1),
      ],
    });
  }
  function deleteItem() {
    if (!remove) return;
    const ids =
      remove.kind === "group"
        ? value.questions
            .filter((q) => q.group_id === remove.id)
            .map((q) => q.id)
        : [remove.id];
    const refs = { ...value.reference_answers };
    ids.forEach((id) => delete refs[id]);
    update({
      groups:
        remove.kind === "group"
          ? value.groups.filter((g) => g.id !== remove.id)
          : value.groups,
      questions: renumber(value.questions.filter((q) => !ids.includes(q.id))),
      reference_answers: refs,
    });
    setRemove(null);
  }
  return (
    <fieldset className="authoring-fieldset" disabled={disabled}>
      <div className="section-heading">
        <h2>{"Question groups"}</h2>
        <button
          type="button"
          className="secondary"
          onClick={() => update({ groups: [...value.groups, newGroup()] })}
        >
          {"Add group"}
        </button>
      </div>
      <p>{"Core questions are required; learners choose one reading group."}</p>
      <div className="group-editor-list">
        {value.groups.map((g, i) => (
          <section className="card form-card group-editor" key={g.id}>
            <div className="section-heading">
              <strong>Group {i + 1}</strong>
              <div className="button-row">
                <button
                  type="button"
                  className="secondary"
                  aria-label={`${"Move group up"} ${g.title}`}
                  disabled={i === 0}
                  onClick={() =>
                    update({ groups: moveItem(value.groups, i, -1) })
                  }
                >
                  ↑
                </button>
                <button
                  type="button"
                  className="secondary"
                  aria-label={`${"Move group down"} ${g.title}`}
                  disabled={i === value.groups.length - 1}
                  onClick={() =>
                    update({ groups: moveItem(value.groups, i, 1) })
                  }
                >
                  ↓
                </button>
                <button
                  type="button"
                  className="text-button danger"
                  onClick={() => setRemove({ kind: "group", id: g.id })}
                >
                  {"Delete group"}
                </button>
              </div>
            </div>
            <div className="form-grid">
              <label>
                {t("title")}
                <input
                  value={g.title}
                  onChange={(e) => gpatch(g.id, { title: e.target.value })}
                />
              </label>
              <label>
                {"Group type"}
                <select
                  aria-label={"Group type"}
                  value={g.kind}
                  onChange={(e) =>
                    gpatch(g.id, { kind: e.target.value as Group["kind"] })
                  }
                >
                  <option value="core">{"Core"}</option>
                  <option value="reading">{"Reading choice"}</option>
                </select>
              </label>
              <label className="span-two">
                {t("description")}
                <textarea
                  rows={2}
                  value={g.description || ""}
                  onChange={(e) =>
                    gpatch(g.id, { description: e.target.value })
                  }
                />
              </label>
            </div>
            <details className="authoring-details">
              <summary>Group identifier</summary>
              <code>{g.id}</code>
            </details>
          </section>
        ))}
      </div>
      <div className="section-heading">
        <h2>
          {t("tasks")} · {value.questions.length}
        </h2>
        <button type="button" className="primary" onClick={addQuestion}>
          {"Add question"}
        </button>
      </div>
      {remove && (
        <div className="notice confirmation">
          <span>
            {remove.kind === "group"
              ? "Delete this group and its questions? Move questions to another group first if you want to retain them."
              : "Delete this question from the content draft? Published editions are unchanged."}
          </span>
          <button
            type="button"
            className="secondary danger"
            onClick={deleteItem}
          >
            {"Delete"}
          </button>
          <button
            type="button"
            className="secondary"
            onClick={() => setRemove(null)}
          >
            {t("cancel")}
          </button>
        </div>
      )}
      {value.questions.map((q, i) => (
        <QuestionCard key={q.id} initiallyOpen={i === 0 || !q.prompt}>
          <summary>
            <span className="session-number">{i + 1}</span>
            <span>
              <strong>
                {value.groups.find((g) => g.id === q.group_id)?.title ||
                  q.group_id}
              </strong>
              <small>
                {q.prompt.slice(0, 100) || "New question · enter a prompt"}
              </small>
            </span>
          </summary>
          <div className="question-edit-body">
            <div className="section-heading">
              <strong>Question {q.ordinal}</strong>
              <div className="button-row">
                <button
                  type="button"
                  className="secondary"
                  aria-label={`${"Move question up"} ${q.id}`}
                  disabled={i === 0}
                  onClick={() =>
                    update({
                      questions: renumber(moveItem(value.questions, i, -1)),
                    })
                  }
                >
                  ↑
                </button>
                <button
                  type="button"
                  className="secondary"
                  aria-label={`${"Move question down"} ${q.id}`}
                  disabled={i === value.questions.length - 1}
                  onClick={() =>
                    update({
                      questions: renumber(moveItem(value.questions, i, 1)),
                    })
                  }
                >
                  ↓
                </button>
                <button
                  type="button"
                  className="text-button danger"
                  onClick={() => setRemove({ kind: "question", id: q.id })}
                >
                  {"Delete question"}
                </button>
              </div>
            </div>
            <div className="form-grid">
              <label>
                {"Group"}
                <select
                  aria-label={"Group"}
                  value={q.group_id}
                  onChange={(e) => qpatch(q.id, { group_id: e.target.value })}
                >
                  {value.groups.map((g) => (
                    <option value={g.id} key={g.id}>
                      {g.title}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {"Question type"}
                <select
                  aria-label={"Question type"}
                  value={q.type}
                  onChange={(e) =>
                    qpatch(q.id, { type: e.target.value as Question["type"] })
                  }
                >
                  {(
                    [
                      "open_response",
                      "reading_response",
                      "fill_in_blank",
                      "single_choice",
                      "image_matching",
                    ] as const
                  ).map((k, j) => (
                    <option key={k} value={k}>
                      {
                        [
                          "Open response",
                          "Reading response",
                          "Fill in blank",
                          "Single choice",
                          "Image matching",
                        ][j]
                      }
                    </option>
                  ))}
                </select>
              </label>
              <label className="span-two">
                {t("prompt")}
                <textarea
                  rows={4}
                  value={q.prompt}
                  onChange={(e) => qpatch(q.id, { prompt: e.target.value })}
                />
              </label>
            </div>
            <details
              className="authoring-details"
              open={
                q.type === "fill_in_blank" ||
                q.type === "single_choice" ||
                q.type === "image_matching"
              }
            >
              <summary>Response format & hints</summary>
              <div className="form-grid">
                <label>
                  {t("answerSlots")}
                  <input
                    type="number"
                    min={1}
                    max={100}
                    value={q.answer_slots}
                    onChange={(e) =>
                      qpatch(q.id, { answer_slots: Number(e.target.value) })
                    }
                  />
                </label>
                <label>
                  {"Non-answer hint"}
                  <input
                    value={q.hint || ""}
                    onChange={(e) => qpatch(q.id, { hint: e.target.value })}
                  />
                </label>
                <label className="span-two">
                  {t("options")}
                  <textarea
                    rows={3}
                    value={q.options.join("\n")}
                    onChange={(e) =>
                      qpatch(q.id, { options: e.target.value.split("\n") })
                    }
                  />
                </label>
              </div>
            </details>
            <section className="authoring-reference">
              <h3>
                Instructor answer / example{" "}
                <HelpPopover label="instructor answer">
                  Private instructor content. Teaching setup controls when
                  students may request an example and how it is delivered.
                </HelpPopover>
              </h3>
              <label>
                Private answer / example
                <textarea
                  rows={4}
                  value={value.reference_answers[q.id] || ""}
                  onChange={(e) =>
                    update({
                      reference_answers: {
                        ...value.reference_answers,
                        [q.id]: e.target.value,
                      },
                    })
                  }
                />
              </label>
            </section>
            <SourceEditor
              question={q}
              materials={materials}
              onChange={(p) => qpatch(q.id, p)}
            />
            <details className="authoring-details">
              <summary>
                Images & original provenance · {q.images.length} images
              </summary>
              <small>
                Question identifier: <code>{q.id}</code>
              </small>
              <label>
                {"Original provenance"}
                <input
                  value={q.source_label}
                  onChange={(e) =>
                    qpatch(q.id, { source_label: e.target.value })
                  }
                />
              </label>
              <div className="section-heading">
                <h3>{"Question images"}</h3>
                <button
                  type="button"
                  className="secondary"
                  onClick={() =>
                    qpatch(q.id, {
                      images: [...q.images, { label: "", url: "", alt: "" }],
                    })
                  }
                >
                  {"Add image"}
                </button>
              </div>
              {q.images.map((img, j) => (
                <div className="image-edit-row" key={j}>
                  {img.url && <img src={img.url} alt={img.alt} />}
                  <label>
                    {"Image URL / protected asset"}
                    <input
                      value={img.url || ""}
                      onChange={(e) =>
                        qpatch(q.id, {
                          images: q.images.map((v, k) =>
                            k === j
                              ? {
                                  ...v,
                                  url: e.target.value,
                                  asset_key: undefined,
                                }
                              : v,
                          ),
                        })
                      }
                    />
                  </label>
                  <label>
                    {"Label"}
                    <input
                      value={img.label}
                      onChange={(e) =>
                        qpatch(q.id, {
                          images: q.images.map((v, k) =>
                            k === j ? { ...v, label: e.target.value } : v,
                          ),
                        })
                      }
                    />
                  </label>
                  <label>
                    {"Accessible description"}
                    <input
                      value={img.alt}
                      onChange={(e) =>
                        qpatch(q.id, {
                          images: q.images.map((v, k) =>
                            k === j ? { ...v, alt: e.target.value } : v,
                          ),
                        })
                      }
                    />
                  </label>
                  <button
                    type="button"
                    className="text-button danger"
                    onClick={() =>
                      qpatch(q.id, {
                        images: q.images.filter((_, k) => k !== j),
                      })
                    }
                  >
                    {"Remove image"}
                  </button>
                </div>
              ))}
            </details>
          </div>
        </QuestionCard>
      ))}
      {authoringErrors(value.groups, value.questions).map((e) => (
        <p className="field-error" key={e}>
          {e}
        </p>
      ))}
    </fieldset>
  );
}
function QuestionCard({
  initiallyOpen,
  children,
}: {
  initiallyOpen: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(initiallyOpen);
  return (
    <details
      className="card question-edit-card"
      open={open}
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      {children}
    </details>
  );
}
export function SourceEditor({
  question: q,
  materials,
  onChange,
}: {
  question: Question;
  materials: Material[];
  onChange: (p: Partial<Question>) => void;
}) {
  const [link, setLink] = useState("");
  const selected = q.source_material_ids || [],
    links = q.source_links || [];
  return (
    <section className="source-editor">
      <h3>
        {"Source scope"}{" "}
        <HelpPopover label="question source scope">
          The tutor uses eligible excerpts from these sources. Teacher-only
          material and instructor answers retain their access rules; selecting a
          source does not make it public.
        </HelpPopover>
      </h3>
      <p>
        {selected.length || links.length
          ? "Only selected sources inform this question. Visibility and private references remain unchanged."
          : "All materials · no selection means all eligible materials in this session, not no sources."}
      </p>
      <details className="source-material-picker">
        <summary>
          {"Select materials"} ·{" "}
          {selected.length
            ? `${selected.length} selected`
            : "No explicit selection"}
        </summary>
        <div className="source-checkboxes">
          {materials.map((m) => (
            <label className="inline-check" key={m.id}>
              <input
                type="checkbox"
                checked={selected.includes(m.id)}
                onChange={(e) =>
                  onChange({
                    source_material_ids: e.target.checked
                      ? [...selected, m.id]
                      : selected.filter((x) => x !== m.id),
                  })
                }
              />
              <span>
                {m.title}
                <small className="block">
                  {m.kind} ·{" "}
                  {m.visibility === "teacher"
                    ? "Teacher only"
                    : "Student visible"}
                </small>
              </span>
            </label>
          ))}
        </div>
      </details>
      {selected
        .filter((id) => !materials.some((m) => m.id === id))
        .map((id) => (
          <div key={id}>
            {id}{" "}
            <button
              type="button"
              className="text-button"
              onClick={() =>
                onChange({
                  source_material_ids: selected.filter((x) => x !== id),
                })
              }
            >
              {"Remove missing selection"}
            </button>
          </div>
        ))}
      <label>
        {"External URL or DOI"}
        <div className="input-action">
          <input
            aria-label="External URL or DOI"
            value={link}
            placeholder="https://… / 10.1234/example"
            onChange={(e) => setLink(e.target.value)}
          />
          <button
            type="button"
            className="secondary"
            disabled={!link.trim()}
            onClick={() => {
              if (!links.includes(link.trim()))
                onChange({ source_links: [...links, link.trim()] });
              setLink("");
            }}
          >
            {"Add source"}
          </button>
        </div>
      </label>
      <small>
        {
          "Inputs are validated by the server on save. Links are synced into Materials; removing this relationship does not delete another question’s or version’s source."
        }
      </small>
      {links.map((v, i) => (
        <div className="input-action" key={i}>
          <input
            aria-label={"Authored source"}
            value={v}
            onChange={(e) =>
              onChange({
                source_links: links.map((x, j) =>
                  j === i ? e.target.value : x,
                ),
              })
            }
          />
          <button
            type="button"
            className="text-button danger"
            onClick={() =>
              onChange({ source_links: links.filter((_, j) => j !== i) })
            }
          >
            {"Remove"}
          </button>
        </div>
      ))}
      {(selected.length > 0 || links.length > 0) && (
        <button
          type="button"
          className="text-button"
          onClick={() =>
            onChange({ source_material_ids: [], source_links: [] })
          }
        >
          {"Use all materials"}
        </button>
      )}
    </section>
  );
}
