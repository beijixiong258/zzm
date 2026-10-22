import { t, systemText } from "./i18n";

export type User = {
  id: string;
  name: string;
  email: string;
  role: "admin" | "teacher" | "student";
  mustChangePassword: boolean;
  archived: boolean;
};
export type Course = {
  id: string;
  title: string;
  code: string;
  description: string;
  systemInstructions?: string;
  joinCode?: string;
  archived: boolean;
};
export type Material = {
  id: string;
  title: string;
  fileName: string;
  relativePath: string;
  mimeType: string;
  status: string;
  visibility: "student" | "teacher";
  errorMessage: string;
  archived: boolean;
  extractionReport?: {
    schemaVersion?: number;
    unitsTotal: number;
    unitsProcessed: number;
    visionUnits?: number;
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
export type TaskContent = {
  description: string;
  learningGoals: string[];
  learningPlan: {
    title: string;
    description: string;
    durationMinutes: number;
  }[];
  openingMessage: string;
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
  errorMessage: string;
  result: TaskContent | null;
};
export type ChatMessage = {
  role: string;
  content: string;
  requestId?: string;
  createdAt?: string;
};
export type LearningRecord = {
  id: string;
  sessionId: string;
  userId: string;
  versionId: string;
  status: string;
  revision: number;
  answers: Record<string, string>;
  messages: ChatMessage[];
  teacherNote: string;
  updatedAt: string;
  submittedAt: string | null;
  reviewedAt: string | null;
};
export type Workspace = { task: Task; record: LearningRecord | null };
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
): Promise<T> {
  const multipart = body instanceof FormData;
  const response = await fetch(`${apiBase}${path}`, {
    method,
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
export const key = (value: string) => encodeURIComponent(value);
export const versionParam = (id?: string) =>
  id ? `?versionId=${key(id)}` : "";
export const fileUrl = (id: string, versionId?: string) =>
  `${apiBase}/materials/${key(id)}/file${versionParam(versionId)}`;
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
        planning: "Generating the learning plan and questions",
        validating: "Validating generated content",
        succeeded: "Ready to apply",
        applied: "Applied to draft",
        failed: "Failed",
        processing: "Processing",
        needsReview: "Review recommended",
        ready: "Ready",
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
