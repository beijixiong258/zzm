export type Role = "admin" | "teacher" | "student";
export type User = {
  id: string;
  name: string;
  email: string;
  role: Role;
  must_change_password?: boolean;
  is_demo?: boolean;
  avatar_url?: string | null;
};
export type FeedbackCategory = "bug" | "idea" | "general";
export type FeedbackStatus = "new" | "reviewed";
export type FeedbackAuthor = Pick<User, "id" | "name" | "email" | "role">;
export type FeedbackItem = {
  id: string;
  request_id: string;
  category: FeedbackCategory;
  subject: string;
  message: string;
  status: FeedbackStatus;
  reply: string;
  created_at: string;
  updated_at: string;
  revision: number;
  author: FeedbackAuthor | null;
};
export type FeedbackPage = { items: FeedbackItem[]; total: number; offset: number; limit: number };
export type FeedbackCreate = { request_id: string; category: FeedbackCategory; subject: string; message: string };
export type FeedbackUpdate = { status: FeedbackStatus; reply: string; expected_revision: number };
export type FeedbackFilters = { offset?: number; limit?: number; category?: FeedbackCategory; status?: FeedbackStatus };
export type ConnectionCheck = {
  status: "not_configured" | "not_checked" | "connected" | "error";
  checked_at: string | null;
  message: string | null;
};
export type SearchSettings = {
  provider: "tavily";
  enabled: boolean;
  configured: boolean;
  api_key_set: boolean;
  api_key_source: "environment" | "saved" | "none";
  connection: ConnectionCheck;
};
export type SearchSettingsPatch = {
  enabled?: boolean;
  api_key?: string;
  clear_api_key?: boolean;
};
export type AiStatus = {
  mode: "demo" | "openai";
  configured: boolean;
  base_url: string;
  model: string;
  last_error?: string | null;
  connection?: ConnectionCheck;
  web_search?: { enabled: boolean; configured: boolean; provider: "tavily"; connection?: ConnectionCheck };
};
export type LiveConnection = {
  status: "connected" | "error" | "checking" | "not_configured" | "unavailable";
  model: string;
  checked_at: string | null;
  expires_at: string | null;
  message: string;
  check_kind: string;
  poll_interval_seconds: number;
  teaching_capacity?: number;
  vision_teaching_capacity?: number;
};
export type AccessSettings = { registration_enabled: boolean };
export type Bootstrap = {
  registration_enabled?: boolean;
  app_name: string;
  demo_enabled: boolean;
  default_locale: "en" | "zh-CN";
  ai: AiStatus;
};
export type Course = {
  id: string;
  code: string;
  title: string;
  description: string;
  student_count: number;
  admin_count: number;
  teacher_count: number;
  join_code?: string;
  published_version_id?: string | null;
  published_version_number?: number | null;
  has_unpublished_changes?: boolean;
  trashed_at?: string | null;
};
export type CourseDetails = Course & {
  trashed_at: string | null;
  session_count: number;
  material_count: number;
  enrollment_count: number;
};
export type CoursePatch = { code?: string; title?: string; description?: string };
export type StudyStatus =
  "not_started" | "in_progress" | "submitted" | "confirmed" | "needs_revision";
export type Availability = {
  active?: boolean;
  starts_at?: string | null;
  ends_at?: string | null;
  effective_active?: boolean;
  availability_reason?:
    "manual_active" | "manual_inactive" | "scheduled" | "not_started" | "ended";
};
export type SessionSummary = Availability & {
  id: string;
  course_id: string;
  title: string;
  subtitle: string;
  number: number;
  status: "draft" | "published";
  question_count: number;
  estimated_minutes: number;
  learning_objectives: string[];
  student_status?: StudyStatus;
};
export type Group = {
  id: string;
  title: string;
  kind: "core" | "reading";
  description?: string;
};
export type QuestionImage = {
  label: string;
  url: string;
  alt: string;
  asset_key?: string;
};
export type Question = {
  id: string;
  group_id: string;
  ordinal: number;
  type:
    | "open_response"
    | "reading_response"
    | "fill_in_blank"
    | "single_choice"
    | "image_matching";
  prompt: string;
  options: string[];
  answer_slots: number;
  images: QuestionImage[];
  source_label: string;
  hint?: string;
  source_material_ids?: string[];
  source_links?: string[];
};
// Optional public cards have no required worksheet group, ordinal or key.
export type PresentedQuestion = Pick<Question, "id" | "type" | "prompt"> &
  Partial<Omit<Question, "id" | "type" | "prompt">> & {
    source_labels?: string[];
  };
export type ExtractionReport = {
  schema_version: 1;
  method: string;
  units_total: number;
  units_processed: number;
  ocr_units: number;
  images_detected: number;
  chars_extracted: number;
  excerpt_chars: number;
  truncated: boolean;
  visual_review_required: boolean;
  failed_units: string[];
  notes: string[];
};
export type CourseMaterial = Material & { session_ids: string[] };
export type Material = {
  source_format?: string | null;
  document?: import("./document-types").DocumentInfo | null;
  processing?: "preview" | "full_document";
  id: string;
  title: string;
  kind: string;
  visibility: "student" | "teacher";
  source_label: string;
  status: "ready" | "processing" | "needs_review" | "error";
  excerpt: string;
  download_url?: string | null;
  warning?: string | null;
  url?: string | null;
  preview_url?: string | null;
  preview_kind?: "pdf" | "text" | "image" | "link" | null;
  extraction_metadata?: Record<string, unknown>;
  extraction_report?: ExtractionReport | null;
};
export type TeachingPhase =
  "warmup" | "worksheet" | "quiz" | "reading" | "wrap_up";
export type TeachingProfile = {
  schema_version: 1;
  background: string;
  student_profile: string;
  response_strategies: string;
  tone: string;
  response_detail: "concise" | "balanced" | "detailed";
  phases: TeachingPhase[];
  reading_focus: string;
  reading_question_count: number;
  reference_delivery: "on_request" | "after_sufficient_answer";
  idle_hint_seconds: number;
  presentation: "full" | "paced";
};
export type TeachingPreviewInput = {
  teaching_profile?: TeachingProfile;
  instructions?: string;
  learning_objectives?: string[];
  teaching_language?: string;
  reference_policy?: "after_attempt" | "after_feedback" | "after_submit";
};
export type TeachingPreview = {
  text: string;
  sections: { id: string; title: string; text: string }[];
  warnings: string[];
};
export type TutorState = {
  phase:
    | "not_started"
    | "warmup"
    | "worksheet"
    | "quiz_offer"
    | "quiz"
    | "reading"
    | "wrap_up"
    | "complete";
  started_at: string | null;
  updated_at: string | null;
  elapsed_seconds: number;
  current_question_id: string | null;
  completed_question_ids: string[];
  question_states: Record<
    string,
    {
      status: "not_started" | "in_progress" | "discussed";
      answer_count: number;
      hint_count: number;
      last_outcome: "unknown" | "needs_retry" | "sufficient";
    }
  >;
  quiz: {
    status: "not_offered" | "offered" | "active" | "completed" | "skipped";
    answered: number;
    total: number;
    correct: number | null;
  };
  reading: { answered: number; total: number };
  presentation: "full" | "paced";
  idle_hint_seconds: number;
  pending_request_id?: string | null;
  last_completed_request_id?: string | null;
};
export type PreviewInfo = {
  id: string | null;
  revision: string | null;
  current_revision: string;
  stale: boolean;
  reset_required: boolean;
  pending: boolean;
  bound_at: string | null;
};
export type SourceReviewInput = TeachingPreviewInput & {
  question_id?: string | null;
  phase?: "warmup" | "worksheet" | "quiz" | "reading" | "wrap_up" | "complete";
};
export type SourceEvidence = {
  material_id: string;
  source_label: string;
  excerpt: string;
  warning?: string | null;
};
export type SourceMaterialReview = {
  id: string;
  title: string;
  kind: string;
  visibility: "student" | "teacher";
  status: string;
  role:
    | "public_knowledge"
    | "private_knowledge"
    | "private_worksheet"
    | "answer_key";
  selected: boolean;
  included: boolean;
  available_chars: number;
  included_chars: number;
  reason: string;
  warning?: string | null;
  extraction_report?: ExtractionReport | null;
};
export type SourceReview = {
  scope: "saved_draft" | "unsaved_instruction_overlay";
  saved_revision: string;
  question_id: string | null;
  phase: string;
  compiled: TeachingPreview;
  public_evidence: SourceEvidence[];
  private_evidence: SourceEvidence[];
  private_reference: {
    question_id: string;
    text: string;
    eligibility: string;
    delivery: string;
  } | null;
  materials: SourceMaterialReview[];
  warnings: string[];
  budgets: {
    public_chars: number;
    private_chars: number;
    request_bytes: number;
  };
};
export type InstructionImportPreview = {
  filename: string;
  text: string;
  status: "ready" | "needs_review" | "error";
  warning: string | null;
  extraction_report: ExtractionReport;
  max_instruction_chars: number;
};
export type TutorTurn = {
  preview_id?: string;
  message: string;
  request_id: string;
  web_search?: boolean;
  action?: "message" | "hint" | "skip_quiz" | "review_question";
  question_id?: string;
};
export type SessionDetail = SessionSummary & {
  teaching_profile?: TeachingProfile;
  instructions: string;
  reference_policy: "after_attempt" | "after_feedback" | "after_submit";
  teaching_language: string;
  groups: Group[];
  questions: Question[];
  materials: Material[];
  reference_answers?: Record<string, string>;
};
export type Attempt = {
  question_id: string;
  answer: string;
  revision_count: number;
  updated_at: string;
  reference_revealed: boolean;
  revisions?: { answer: string; created_at: string }[];
};
export type Message = {
  presented_question_id?: string | null;
  metadata?: {
    phase?: TutorState["phase"];
    kind?: string;
    presented_question?: PresentedQuestion;
    reading_choices?: Pick<Group, "id" | "title" | "description">[];
    reference_question_id?: string;
    narrative_text?: string;
    presentation_text?: string;
    formative_outcome?: "unknown" | "needs_retry" | "sufficient";
    document_read_coverage?: {
      material_id: string;
      revision_id: string;
      source_label: string;
      read_characters: number;
      available_characters: number;
      eligible_text_complete: boolean;
      unresolved_blocks: number;
      excluded_blocks: number;
      all_stored_regions_read: boolean;
      next_page: number | null;
      visual_read_pages?: number;
      available_image_pages?: number;
      visual_read_complete?: boolean;
      text_view_id?: string;
      alternative_text_blocks?: number;
      alternative_text_characters?: number;
      alternative_unresolved_blocks?: number;
      alternative_excluded_blocks?: number;
    }[];
  };
  id: string;
  role: "user" | "assistant";
  content: string;
  question_id: string | null;
  created_at: string;
  mode: "demo" | "openai" | "system";
  intent?: "answer" | "ask";
  citations?: {
    source_label: string;
    text?: string;
    url?: string;
    kind?: "web" | "document" | "document_supplement" | "file";
    quote?: string;
    quote_basis?: "rendered_html_cell_line_breaks";
    quote_char_start?: number;
    quote_char_end?: number;
    material_id?: string;
    revision_id?: string;
    page?: number | null;
    supplement_id?: string;
    source_part?: string;
    source_kind?: string;
    printed_label?: string | null;
    block_id?: string | null;
    evidence_kind?: "source_image";
    source_image_sha256?: string;
    version_id?: string | null;
  }[];
};
export type Submission = {
  status: StudyStatus;
  submitted_at: string | null;
  reviewed_at: string | null;
  teacher_note: string;
};
export type Progress = {
  answered: number;
  total: number;
  active_question_ids: string[];
  current_question_id: string | null;
};
export type VersionChoice = { id: string; number: number; label: string };
export type WorkspaceVersion = {
  id: string | null;
  number: number | null;
  is_current: boolean;
  is_draft: boolean;
};
export type Workspace = {
  preview?: PreviewInfo | null;
  tutor?: TutorState;
  session: SessionDetail;
  user: User;
  selected_reading: string | null;
  attempts: Record<string, Attempt>;
  messages: Message[];
  progress: Progress;
  submission: Submission;
  ai: AiStatus;
  version?: WorkspaceVersion;
  available_versions?: VersionChoice[];
  read_only?: boolean;
  read_only_reason?: string | null;
};
export type StudentRow = {
  user: User;
  answered: number;
  total: number;
  selected_reading: string | null;
  status: StudyStatus;
  last_active: string | null;
  submitted_at: string | null;
  version?: WorkspaceVersion;
};
export type Settings = { ai: AiStatus; api_key_set: boolean };
export type Reference = {
  question_id: string;
  reference: string;
  source_label: string;
};
export type SessionPatch = Partial<
  Pick<
    SessionDetail,
    | "number"
    | "title"
    | "subtitle"
    | "instructions"
    | "teaching_profile"
    | "learning_objectives"
    | "reference_policy"
    | "teaching_language"
    | "status"
    | "questions"
    | "groups"
    | "reference_answers"
    | "active"
    | "starts_at"
    | "ends_at"
  >
>;
export type RosterEntry = {
  user: User;
  archived_at: string | null;
  purge_at: string | null;
  has_work: boolean;
};
export type RosterPreview = {
  import_id: string;
  rows: {
    row_number: number;
    name: string;
    email: string;
    action: "create" | "enroll" | "restore" | "skip" | "error";
    errors: string[];
    warnings: string[];
  }[];
  valid_count: number;
  error_count: number;
};
export type LearningRun = {
  course: { id: string; code: string; title: string };
  session: { id: string; title: string; number: number };
  version: VersionChoice;
  status: StudyStatus;
  answered: number;
  total: number;
  last_active: string | null;
};
export type RosterResult = {
  created: number;
  enrolled: number;
  restored: number;
  skipped: number;
};
export type VersionEntry = VersionChoice & {
  created_at: string;
  created_by: string;
};
export type VersionList = {
  current_version_id: string | null;
  has_unpublished_changes: boolean;
  versions: VersionEntry[];
};
export type VersionSnapshot = VersionEntry & {
  course: Course;
  sessions: SessionDetail[];
};
export type VersionDiff = {
  changes: { path: string; before: unknown; after: unknown }[];
};
export type WorksheetDraft = {
  title: string;
  groups: Group[];
  questions: Question[];
  reference_answers: Record<string, string>;
};
export type WorksheetPreview = {
  import_id: string;
  material: Material;
  draft: WorksheetDraft;
  warnings: string[];
  method: string;
  assets: { key: string; label: string; url: string }[];
  needs_review: boolean;
};
