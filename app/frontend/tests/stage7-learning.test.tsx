import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import fixture from "./stage7-learning-fixture.json";
import type {
  Course,
  CourseMaterial,
  SessionDetail,
  Workspace,
} from "../src/types";
import Home from "../src/Home";
import Authoring from "../src/Authoring";
import Materials from "../src/Materials";
import CourseLibrary, { filterCourseMaterials } from "../src/CourseLibrary";
import SavedResponses from "../src/SavedResponses";
import TeacherProcessOverview from "../src/TeacherProcessOverview";
import { QuestionPrompt, TutorMessage } from "../src/TutorMessage";
const noop = () => {};
const materials = fixture.materials as CourseMaterial[];
const session = fixture.sessions[0] as SessionDetail;
const workspace = fixture.workspace as Workspace;
const record = fixture.record as Workspace;
const home = (staff = true) =>
  renderToStaticMarkup(
    <Home
      user={{ ...workspace.user, role: staff ? "teacher" : "student" }}
      courses={[fixture.course as Course]}
      sessionMap={{ "fixture-course": fixture.sessions as SessionDetail[] }}
      loading={false}
      history={false}
      onOpen={noop}
      onPreview={noop}
      onRefresh={async () => {}}
      onRoster={noop}
      onVersions={noop}
      onMaterials={noop}
    />,
  );
const responses = (w = workspace, teacherRecord = false) =>
  renderToStaticMarkup(
    <SavedResponses
      workspace={w}
      selected="fixture-question"
      viewerId="fixture-student"
      locked={teacherRecord}
      busy={false}
      teacherRecord={teacherRecord}
      references={{}}
      onSelect={noop}
      onDiscuss={noop}
      onSave={async () => true}
      onReveal={noop}
      onUseDraft={noop}
      onStorageWarning={noop}
    />,
  );
describe("Stage7 course and learning rollout", () => {
  it("lists canonical files once while retaining multi-session memberships", () => {
    expect(materials).toHaveLength(3);
    expect(
      filterCourseMaterials(materials, "", "", "fixture-session").map(
        (m) => m.id,
      ),
    ).toEqual(["fixture-reading", "fixture-private"]);
  });
  it("searches title/source/type, not hidden excerpts", () => {
    expect(
      filterCourseMaterials(materials, "  ASSESSMENT  ", "", ""),
    ).toHaveLength(1);
    expect(
      filterCourseMaterials(materials, "decisions depend", "", ""),
    ).toHaveLength(0);
  });
  it("retains unlinked canonical material as a useful library filter", () => {
    expect(
      filterCourseMaterials(materials, "", "", "unlinked").map((m) => m.id),
    ).toEqual(["fixture-unlinked"]);
  });
  it("combines private visibility and session filters without rewriting source data", () => {
    const before = JSON.stringify(materials);
    expect(
      filterCourseMaterials(materials, "", "teacher", "fixture-session-two"),
    ).toHaveLength(0);
    expect(JSON.stringify(materials)).toBe(before);
  });
  it("has no unsupported upload action at course scope", () => {
    const html = renderToStaticMarkup(
      <CourseLibrary courseId="fixture-course" onOpenSession={noop} />,
    );
    expect(html).not.toContain('type="file"');
    expect(html).toContain("Course materials");
  });
  it("Home shows true publication state and course counts without progress bars", () => {
    const html = home();
    expect(html).toContain("Published edition 3");
    expect(html).toContain("Unpublished changes");
    expect(html).toContain("12");
    expect(html).not.toMatch(/progressbar|prepared|mastered/i);
  });
  it("Home provides a primary per session and course-only destinations", () => {
    const html = home();
    expect(html.match(/class="primary"/g) || []).toHaveLength(2);
    expect(html).toContain("Teaching setup");
    expect(html).toContain("Version history");
    expect(html).toContain("Course materials");
  });
  it("students do not receive owner-only course actions", () => {
    const html = home(false);
    expect(html).not.toContain("Course materials");
    expect(html).not.toContain("Learners</button>");
  });
  it("private files stay absent from student material markup", () => {
    const html = renderToStaticMarkup(
      <Materials materials={materials} versionId="edition-3" />,
    );
    expect(html).not.toContain("Instructor notes");
    expect(html).toContain("version_id=edition-3");
  });
  it("material coverage is collapsed but review-required warnings stay visible", () => {
    const html = renderToStaticMarkup(
      <Materials materials={materials} teacher />,
    );
    expect(html).toContain('<details class="material-extraction-details">');
    expect(html).toContain("OCR needs visual review before publishing");
    expect(html).toContain("Page 8 could not be read");
  });
  it("separates a private instructor answer from the public prompt and stable IDs", () => {
    const html = renderToStaticMarkup(
      <Authoring
        value={{
          title: "Worksheet",
          groups: session.groups,
          questions: session.questions,
          reference_answers: session.reference_answers || {},
        }}
        onChange={noop}
        materials={materials}
      />,
    );
    expect(html).toContain("Private answer / example");
    expect(html).toContain("Source scope");
    expect(html).toContain("Group identifier");
    expect(html).toContain("Images &amp; original provenance");
  });
  it("reference button stays visibly gated until submission", () => {
    const html = responses();
    expect(html).toContain("Available after submitting your work.");
    expect(html).toMatch(/disabled=""[^>]*>Request instructor example/);
  });
  it("teacher record retains actual private examples and saved revision text", () => {
    const html = responses(record, true);
    expect(html).toContain("Private instructor example from labelled fixture.");
    expect(html).toContain("I would check the score.");
    expect(html).toContain("Earlier responses");
  });
  it("process inspection is collapsed while exact original-message navigation remains", () => {
    const html = renderToStaticMarkup(
      <TeacherProcessOverview
        workspace={record}
        onMessage={noop}
        onResponse={noop}
      />,
    );
    expect(html).toContain('<details class="process-details">');
    expect(html).toContain("Related original messages");
    expect(html).toContain("Locate latest reply");
    expect(html).toContain("Responses &amp; revisions");
    expect(html).not.toContain('process-details" open');
  });
  it("question sources are inspectable without altering the public question", () => {
    const q = session.questions[0];
    const before = JSON.stringify(q);
    const html = renderToStaticMarkup(
      <QuestionPrompt question={q} workspace={workspace} />,
    );
    expect(html).toContain("Sources · 1");
    expect(html).toContain(q.prompt);
    expect(JSON.stringify(q)).toBe(before);
  });
  it("raw learner whitespace and historical demo attribution remain intact", () => {
    const message = {
      ...workspace.messages[0],
      content: "Original\nsecond line",
    };
    const html = renderToStaticMarkup(
      <TutorMessage
        message={message}
        workspace={workspace}
        latest={false}
        paced={false}
        onQuestion={noop}
      />,
    );
    expect(html).toContain("Original\nsecond line");
    const old = renderToStaticMarkup(
      <TutorMessage
        message={{ ...workspace.messages[1], mode: "demo" }}
        workspace={workspace}
        latest={false}
        paced={false}
        onQuestion={noop}
      />,
    );
    expect(old).toContain("Recorded demo");
  });
  it("student markup never includes the server-only instructor answer", () => {
    const html = responses();
    expect(html).not.toContain("Private instructor example");
  });
});
vi.restoreAllMocks();
