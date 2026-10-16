import { t, dateLocale, systemText } from "../i18n";
export const errorText = (error: unknown) =>
  error instanceof Error
    ? systemText(error.message)
    : t("The operation failed. Please try again.");
export const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value));
export const dateText = (value?: string | null) =>
  value
    ? new Date(value).toLocaleString(dateLocale(), {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "—";
export const label = (value: string) =>
  ({
    open_response: t("Open response"),
    reading_response: t("Reading response"),
    fill_in_blank: t("Fill in the blank"),
    single_choice: t("Single choice"),
    image_matching: t("Image matching"),
    answer_key: t("Answer key"),
    not_started: t("Not started"),
    in_progress: t("In progress"),
    needs_revision: t("Needs revision"),
    needs_review: t("Needs review"),
    confirmed: t("Confirmed"),
    submitted: t("Submitted"),
    published: t("Included in publication"),
    draft: t("Draft only"),
    reading: t("Reading"),
    worksheet: t("Worksheet"),
    reference: t("Reference"),
    slides: t("Slides"),
    link: t("Link"),
    ready: t("Ready"),
    processing: t("Processing"),
    error: t("Needs attention"),
    create: t("Create account"),
    enroll: t("Join course"),
    restore: t("Restore"),
    skip: t("Skip"),
    extracted: t("Extracted"),
    approved: t("Checked and approved"),
    excluded: t("Exclude from teaching"),
    general: t("General"),
    bug: t("Issue"),
    idea: t("Suggestion"),
    roster: t("Course people"),
    queued: t("Queued"),
    uploading: t("Uploading"),
    uploaded: t("Uploaded"),
    failed: t("Failed"),
    teacher: t("Teacher"),
    admin: t("Administrator"),
    student: t("Student"),
    home: t("Home"),
    history: t("History"),
    library: t("Library"),
    versions: t("Versions"),
    record: t("Record"),
    accounts: t("Accounts"),
    settings: t("Settings"),
    profile: t("Profile"),
    people: t("People"),
    workspace: t("Learning workspace"),
    preview: t("Preview"),
  })[value] ?? value;
