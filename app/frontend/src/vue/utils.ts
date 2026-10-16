export const errorText = (error: unknown) =>
  error instanceof Error
    ? error.message
    : "The operation failed. Please try again.";
export const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value));
export const dateText = (value?: string | null) =>
  value
    ? new Date(value).toLocaleString("en-GB", {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "—";
export const label = (value: string) =>
  ({
    open_response: "Open response",
    reading_response: "Reading response",
    fill_in_blank: "Fill in the blank",
    single_choice: "Single choice",
    image_matching: "Image matching",
    answer_key: "Answer key",
    not_started: "Not started",
    in_progress: "In progress",
    needs_revision: "Needs revision",
    needs_review: "Needs review",
    confirmed: "Confirmed",
    submitted: "Submitted",
    published: "Included in publication",
    draft: "Draft only",
    reading: "Reading",
    worksheet: "Worksheet",
    reference: "Reference",
    slides: "Slides",
    link: "Link",
    ready: "Ready",
    processing: "Processing",
    error: "Needs attention",
  })[value] ?? value;
