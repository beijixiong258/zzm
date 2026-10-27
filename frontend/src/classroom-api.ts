import { t, systemText } from "./i18n";

export type User = {
  id: string;
  name: string;
  email: string;
  username?: string;
  invitationEnabled?: boolean;
  demo?: boolean;
  role: "admin" | "teacher" | "student";
  mustChangePassword: boolean;
  archived: boolean;
};
export type Course = {
  workspace: boolean;
  id: string;
  title: string;
  code: string;
  description: string;
  courseInformation?: string;
  studentProfile?: string;
  systemInstructions?: string;
  joinCode?: string;
  archived: boolean;
};
export type Material = {
  id: string;
  title: string;
  fileName: string;
  fileSize?: number;
  relativePath: string;
  mimeType: string;
  status: string;
  visibility: "student" | "teacher";
  errorMessage: string;
  archived: boolean;
  recordId?: string;
  questionId?: string;
  extractionReport?: {
    schemaVersion?: number;
    currentUnit?: string;
    pdfInputMode?: "inspecting" | "text" | "images" | "";
    unitsInspected?: number;
    imageInputTokensEstimated?: number;
    pageInputs?: {
      page: number;
      kind: "text" | "image";
      textCharacters: number;
      width: number;
      height: number;
      originalWidth: number;
      originalHeight: number;
      cropped: boolean;
      imageBytes: number;
      imageTokensEstimated?: number;
      status: string;
    }[];
    unitsTotal: number;
    unitsProcessed: number;
    visionUnits?: number;
    nativeTextUnits?: number;
    visionInputTokensEstimated?: number;
    visionPromptTokensActual?: number;
    textTokensEstimated?: number;
    textTokensUpperBound?: number;
    textCharacters?: number;
    truncated: boolean;
    visualReviewRequired: boolean;
    failedUnits: string[];
    notes: string[];
  } | null;
};
export type Question = {
  id: string;
  type: string;
  prompt: string;
  options: string[];
  answerSlots: number;
  referenceAnswer?: string;
  explanation?: string;
  hint: string;
  sourceMaterialIds: string[];
  imageMaterialIds: string[];
};
export type Diagram = {
  id: string;
  title: string;
  nodes: { id: string; text: string; x: number; y: number }[];
  edges: { from: string; to: string; label: string }[];
};
export type ContextUsage = {
  window: number;
  inputLimit?: number;
  inputRemaining?: number;
  contextRemaining?: number;
  inputEstimate: number;
  inputUpperBound: number;
  imageEstimate: number;
  outputReserve: number;
  safetyReserve: number;
  remaining: number;
  tokenEstimateOnly?: boolean;
  estimatedOverReference?: boolean;
  materialsReady?: boolean;
  revisionBudget?: ContextUsage;
  incompleteMaterials?: string[];
  pendingMaterials?: string[];
  promptTokensActual?: number;
  completionTokensActual?: number;
  totalTokensActual?: number;
};
export type TaskContent = {
  description: string;
  learningGoals: string[];
  learningPlan: {
    title: string;
    description: string;
    durationMinutes: number;
  }[];
  openingMessage: string;
  handout?: string;
  teachingMode?: "guided" | "autonomous";
  feedbackMode?: "immediate" | "teacherReview";
  rubric?: string;
  diagrams?: Diagram[];
  illustrationMaterialIds?: string[];
  questions: Question[];
  aiConfig?: {
    teachingApproach: string;
    feedbackStrategy: string;
    responseDetail: string;
    tone: string;
  };
};
export type Task = {
  id: string;
  courseId: string;
  title: string;
  description: string;
  sessionType: "tutor" | "assignment";
  topic: string;
  learningGoals: string;
  additionalInstructions?: string;
  teachingLanguage: "zh-CN" | "en";
  materialIds: string[];
  content: TaskContent;
  materials: Material[];
  revision: number;
  versionId?: string;
  publishedVersionId: string | null;
  archived: boolean;
};
export type Job = {
  id: string;
  sessionId: string;
  expectedRevision: number;
  status: string;
  stage: string;
  progressCharacters?: number;
  errorMessage: string;
  diagnosticResponse?: string | null;
  result: TaskContent | null;
  usage?: ContextUsage;
};
export type TeacherReply = {
  message: string;
  fields: Record<string, string>;
  action: string;
  usage?: ContextUsage;
};
export type ChatMessage = {
  role: string;
  content: string;
  requestId?: string;
  attachmentIds?: string[];
  pendingReview?: boolean;
  usage?: ContextUsage;
  createdAt?: string;
};
export type LearningRecord = {
  removedAttachments: Record<string, string>;
  id: string;
  sessionId: string;
  userId: string;
  versionId: string;
  status: string;
  revision: number;
  answers: Record<string, string>;
  messages: ChatMessage[];
  messageCount?: number;
  messageLimit?: number;
  messagesTruncated?: boolean;
  conversationLimitReached?: boolean;
  attachmentMaxBytes?: number;
  answerHistoryCount?: number;
  conversationHistoryCount?: number;
  historyTruncated?: boolean;
  answerHistory?: {
    id?: string;
    revision: number;
    savedAt: string;
    answers: Record<string, string>;
  }[];
  conversationHistory?: {
    id: string;
    archivedAt: string;
    messageCount: number;
  }[];
  teacherNote: string;
  updatedAt: string;
  submittedAt: string | null;
  reviewedAt: string | null;
};
export type LearningRecordSummary = Pick<
  LearningRecord,
  "id" | "sessionId" | "versionId" | "userId" | "status" | "updatedAt"
>;
export type Workspace = {
  task: Task;
  record: LearningRecord | null;
  attachments?: Material[];
};
export type TaskSummary = Pick<
  Task,
  | "id"
  | "courseId"
  | "title"
  | "description"
  | "sessionType"
  | "archived"
  | "publishedVersionId"
  | "revision"
>;
export type StudentRow = {
  userId: string;
  name: string;
  email: string;
  username?: string;
  invitationEnabled?: boolean;
  demo?: boolean;
  recordId: string | null;
  versionId: string | null;
  status: string;
  submissionStatus: string;
  answered: number;
  total: number;
  lastActive: string | null;
};
export type Member = User & {
  membershipRole: string;
  membershipArchived: boolean;
};
export type Version = {
  id: string;
  revision: number;
  label: string;
  createdAt: string;
};
export type Bootstrap = {
  needsSetup: boolean;
  defaultLocale: string;
  demoEnabled: boolean;
  demoAccounts: User[];
};

const configured = import.meta.env.VITE_API_BASE_URL as string | undefined;
export const apiBase = (
  configured ||
  `${location.protocol}//${location.hostname.includes(":") ? `[${location.hostname}]` : location.hostname}:8001/api`
).replace(/\/$/, "");
export class RequestError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export async function call<T>(
  path: string,
  method = "GET",
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const multipart = body instanceof FormData;
  const response = await fetch(`${apiBase}${path}`, {
    method,
    signal,
    credentials: "include",
    headers:
      body == null || multipart ? {} : { "Content-Type": "application/json" },
    body: body == null ? undefined : multipart ? body : JSON.stringify(body),
  }).catch(() => {
    throw new RequestError(
      0,
      t(
        "Cannot connect to the backend. Check that it is running on port 8001.",
      ),
    );
  });
  if (!response.ok) {
    const data = (await response.json().catch(() => ({}))) as {
      detail?: string;
    };
    throw new RequestError(
      response.status,
      systemText(data.detail || t("Request failed ({0})", [response.status])),
    );
  }
  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}
export function upload<T>(
  path: string,
  body: FormData,
  onProgress: (value: number) => void,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", apiBase + path);
    request.withCredentials = true;
    request.timeout = 120000;
    request.upload.onprogress = (event) => {
      if (event.lengthComputable)
        onProgress(Math.min(100, (event.loaded / event.total) * 100));
    };
    request.onload = () => {
      let data: { detail?: string } & T;
      try {
        data = JSON.parse(request.responseText || "{}");
      } catch {
        reject(
          new RequestError(
            request.status,
            t("The server returned an invalid response."),
          ),
        );
        return;
      }
      if (request.status >= 200 && request.status < 300) resolve(data);
      else
        reject(
          new RequestError(
            request.status,
            systemText(
              data.detail || t("Upload failed ({0})", [request.status]),
            ),
          ),
        );
    };
    request.onerror = () =>
      reject(
        new RequestError(
          0,
          t("Upload failed. Check your connection and try again."),
        ),
      );
    request.ontimeout = () =>
      reject(
        new RequestError(
          0,
          t("Upload timed out. Check the material list before retrying."),
        ),
      );
    request.send(body);
  });
}
export async function download(path: string, filename: string) {
  const response = await fetch(`${apiBase}${path}`, { credentials: "include" });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new RequestError(
      response.status,
      systemText(data.detail || t("Export failed.")),
    );
  }
  const url = URL.createObjectURL(await response.blob()),
    anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename.replace(/[\\/:*?"<>|]/g, "_");
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export const key = (value: string) => encodeURIComponent(value);
export const versionParam = (id?: string) =>
  id ? `?versionId=${key(id)}` : "";
export const fileUrl = (id: string, versionId?: string) =>
  `${apiBase}/materials/${key(id)}/file${versionParam(versionId)}`;
export function multipleChoiceAnswers(
  answer = "",
  options: string[] = [],
): string[] {
  if (!answer.trim()) return [];
  try {
    const values: unknown = JSON.parse(answer);
    if (
      Array.isArray(values) &&
      values.every(
        (value) =>
          typeof value === "string" &&
          (!options.length || options.includes(value)),
      )
    )
      return values;
  } catch {
    // Existing records use newline-separated option text.
  }
  if (options.includes(answer)) return [answer];
  return answer.split(/\r?\n/).filter((value) => value.length > 0);
}
export function answerText(
  question: Question | undefined,
  answer = "",
): string {
  return question?.type === "multipleChoice"
    ? multipleChoiceAnswers(answer, question.options).join("\n\n")
    : answer;
}
export function blankTask(courseId: string): Task {
  return {
    id: "",
    courseId,
    title: "",
    description: "",
    sessionType: "tutor",
    topic: "",
    learningGoals: "",
    additionalInstructions: "",
    teachingLanguage: "zh-CN",
    materialIds: [],
    content: {
      description: "",
      learningGoals: [],
      learningPlan: [],
      openingMessage: "",
      handout: "",
      teachingMode: "guided",
      feedbackMode: "immediate",
      rubric: "",
      diagrams: [],
      questions: [],
    },
    materials: [],
    revision: 0,
    publishedVersionId: null,
    archived: false,
  };
}
export function studentTask(task: Task): Task {
  const copy = JSON.parse(JSON.stringify(task)) as Task;
  delete copy.additionalInstructions;
  delete copy.content.aiConfig;
  delete copy.content.rubric;
  for (const question of copy.content.questions) {
    delete question.referenceAnswer;
    delete question.explanation;
  }
  copy.materials = copy.materials.filter((m) => m.visibility === "student");
  copy.materialIds = copy.materials.map((m) => m.id);
  if (copy.learningGoals.trim())
    copy.content.learningGoals = copy.learningGoals
      .split("\n")
      .filter((line) => line.trim());
  return copy;
}
export function statusText(status: string) {
  return t(
    (
      {
        notStarted: "Not started",
        inProgress: "In progress",
        completed: "Completed",
        confirmed: "Completed",
        submitted: "Awaiting teacher review",
        needsRevision: "Revision requested",
        queued: "Queued",
        running: "Generating",
        planning: "Preparing generation",
        drafting: "Writing the lesson and practice",
        validating: "Validating generated content",
        succeeded: "Ready to apply",
        applied: "Applied to draft",
        failed: "Failed",
        processing: "Processing",
        incomplete: "Incomplete extraction",
        needsReview: "Processing complete",
        ready: "Processing complete",
      } as Record<string, string>
    )[status] || status,
  );
}
export const questionTypes = {
  openResponse: "Open response",
  readingResponse: "Reading response",
  fillInBlank: "Fill in the blanks",
  singleChoice: "Single choice",
  multipleChoice: "Multiple choice",
  trueFalse: "True or false",
  imageMatching: "Image matching",
};
export function dateText(value?: string | null) {
  return value
    ? new Date(
        value.endsWith("Z") || /[+-]\d\d:\d\d$/.test(value)
          ? value
          : value + "Z",
      ).toLocaleString()
    : "—";
}
