import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  composerEnterAction,
  questionPresentationText,
  tutorNarrative,
} from "../src/guided-study";
import { TutorMessage } from "../src/TutorMessage";
import { fixtureWorkspace } from "./fixtures";
import type { Message, PresentedQuestion, TutorState } from "../src/types";

const question: PresentedQuestion = {
  id: "stage4-quiz-3",
  type: "single_choice",
  prompt:
    "Placeholder formative item 3: Which approach best supports a learner who is stuck?",
  options: [
    "Give the full answer immediately",
    "Provide a focused hint and invite a new attempt",
    "Move on to the next question",
    "Ask them to memorise the solution",
  ],
  images: [],
};
const feedback =
  "You chose option B. That’s exactly right.\n\nFormative practice: correct. Guided feedback supports targeted revision.";
function reply(phase: TutorState["phase"] = "quiz"): Message {
  return {
    id: "stage4-feedback",
    role: "assistant",
    mode: "demo",
    question_id: null,
    created_at: "2026-10-07T04:01:00Z",
    content: feedback + questionPresentationText(question, phase),
    presented_question_id: question.id,
    metadata: { phase, presented_question: question },
  };
}

describe("stage4 corrected composer keyboard contract", () => {
  it.each([
    [{ key: "Enter" }, false, "send"],
    [{ key: "Enter", shiftKey: true }, false, "native"],
    [{ key: "Enter", ctrlKey: true }, false, "ignore"],
    [{ key: "Enter", metaKey: true }, false, "ignore"],
    [{ key: "Enter", altKey: true }, false, "ignore"],
    [{ key: "Enter", shiftKey: true, ctrlKey: true }, false, "ignore"],
    [{ key: "Enter", shiftKey: true, metaKey: true }, false, "ignore"],
    [{ key: "Enter", shiftKey: true, altKey: true }, false, "ignore"],
    [{ key: "Enter", repeat: true }, false, "ignore"],
    [{ key: "Enter", isComposing: true }, false, "native"],
    [{ key: "Enter", keyCode: 229 }, false, "native"],
    [{ key: "Enter" }, true, "native"],
    [{ key: "Enter", ctrlKey: true, isComposing: true }, false, "native"],
    [{ key: "Process", keyCode: 229 }, false, "native"],
    [{ key: "a" }, false, "native"],
  ] as const)(
    "handles %j (composition=%s) as %s",
    (event, composing, expected) => {
      expect(composerEnterAction(event, composing)).toBe(expected);
    },
  );
});

describe("stage4 exact presentation deduplication, no raw-history edits", () => {
  it("uses explicit validated parts for new replies and preserves raw content/metadata", () => {
    const message = reply();
    const metadata = {
      ...message.metadata,
      narrative_text: feedback,
      presentation_text: questionPresentationText(question, "quiz"),
    };
    const original = JSON.stringify({ ...message, metadata });
    expect(tutorNarrative({ ...message, metadata }, question)).toBe(feedback);
    expect(JSON.stringify({ ...message, metadata })).toBe(original);
  });
  it.each(["quiz", "reading", "worksheet"] as const)(
    "suppresses only the known exact legacy %s suffix",
    (phase) => {
      expect(tutorNarrative(reply(phase), question)).toBe(feedback);
    },
  );
  it("retains top feedback and four structured options, with each question/option only once", () => {
    const workspace = fixtureWorkspace(),
      message = reply();
    const before = JSON.stringify(message);
    const html = renderToStaticMarkup(
      <TutorMessage
        message={message}
        workspace={workspace}
        latest
        paced={false}
        onQuestion={() => {}}
      />,
    );
    expect(html).toContain("You chose option B.");
    expect(html).toContain("Formative practice: correct.");
    for (const text of [question.prompt, ...(question.options || [])])
      expect(html.split(text)).toHaveLength(2);
    expect(html).not.toContain("Optional formative practice:");
    expect(html).toContain('data-question-id="stage4-quiz-3"');
    expect(JSON.stringify(message)).toBe(before);
  });
  it("paces feedback only, never resurrects the duplicate suffix as a reading section", () => {
    const html = renderToStaticMarkup(
      <TutorMessage
        message={reply()}
        workspace={fixtureWorkspace()}
        latest
        paced
        onQuestion={() => {}}
      />,
    );
    expect(html).toContain("Paced reading · 1 of 2 sections");
    expect(html.split(question.prompt)).toHaveLength(2);
  });
  it("retains a server-inserted instructor comparison when explicit engine narrative is stale", () => {
    const message = reply();
    const comparison =
      "\n\nInstructor reference comparison (not a formal grade):\nPublicly eligible example.";
    const suffix = questionPresentationText(question, "quiz");
    expect(
      tutorNarrative(
        {
          ...message,
          content: feedback + comparison + suffix,
          metadata: {
            ...message.metadata,
            narrative_text: feedback,
            presentation_text: suffix,
          },
        },
        question,
      ),
    ).toBe(feedback + comparison);
  });
  it.each([
    (suffix: string) => suffix + "\nAdditional educational explanation.",
    (suffix: string) => suffix.replace("1. ", "A. "),
    (suffix: string) => suffix.replace(":\n", ": "),
    (suffix: string) => suffix + " ",
    (suffix: string) =>
      suffix.replace("Optional formative practice", "Practice notes"),
  ])(
    "does not delete a lookalike or nonterminal educational block",
    (change) => {
      const message = reply(),
        content = feedback + change(questionPresentationText(question, "quiz"));
      expect(tutorNarrative({ ...message, content }, question)).toBe(content);
    },
  );
  it("preserves repeated question/options inside feedback and removes only the last appended copy", () => {
    const suffix = questionPresentationText(question, "quiz"),
      narrative =
        "Discuss these options:" +
        suffix +
        "\n\nThis is meaningful explanation.";
    expect(
      tutorNarrative({ ...reply(), content: narrative + suffix }, question),
    ).toBe(narrative);
  });
  it("never hides text without a card, in user messages, or under mismatched prompt metadata", () => {
    const message = reply();
    expect(tutorNarrative(message)).toBe(message.content);
    expect(tutorNarrative({ ...message, role: "user" }, question)).toBe(
      message.content,
    );
    expect(
      tutorNarrative(message, {
        ...question,
        prompt: "Different stored prompt",
      }),
    ).toBe(message.content);
  });
  it("retains quiz invitation and wrap-up summaries without a question card", () => {
    for (const content of [
      "Would you like an optional five-question formative quiz?",
      "Discussion summary: not a formal grade.",
    ]) {
      expect(
        tutorNarrative({
          role: "assistant",
          content,
          metadata: { narrative_text: "Short", presentation_text: "Other" },
        }),
      ).toBe(content);
    }
  });
  it("matches the known figure suffix and retains figures and every source label", () => {
    const presented = {
      ...question,
      type: "reading_response" as const,
      images: [
        {
          label: "A",
          alt: "Synthetic figure",
          url: "/api/assets/stage4-fixture.svg",
        },
      ],
      source_labels: ["Source one", "Source two"],
    };
    const suffix = questionPresentationText(presented, "reading");
    expect(
      suffix.endsWith(
        "Refer to the configured figures shown with this question.",
      ),
    ).toBe(true);
    const message = {
      ...reply("reading"),
      content: feedback + suffix,
      metadata: { phase: "reading" as const, presented_question: presented },
    };
    const html = renderToStaticMarkup(
      <TutorMessage
        message={message}
        workspace={fixtureWorkspace()}
        latest
        paced={false}
        onQuestion={() => {}}
      />,
    );
    expect(html).toContain("Synthetic figure");
    expect(html).toContain("Source one");
    expect(html).toContain("Source two");
    expect(html).not.toContain("Refer to the configured figures");
  });
});
