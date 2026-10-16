import type {
  Bootstrap,
  AccessSettings,
  User,
  Role,
  Course,
  CourseDetails,
  CoursePatch,
  SessionSummary,
  SessionDetail,
  Workspace,
  StudentRow,
  Settings,
  SearchSettings,
  SearchSettingsPatch,
  ConnectionCheck,
  AiStatus,
  LiveConnection,
  Reference,
  SessionPatch,
  Material,
  CourseMaterial,
  RosterEntry,
  RosterPreview,
  RosterResult,
  VersionList,
  VersionEntry,
  VersionSnapshot,
  VersionDiff,
  WorksheetPreview,
  WorksheetDraft,
  LearningRun,
  TeachingPreview,
  TeachingPreviewInput,
  TutorTurn,
  PreviewInfo,
  SourceReview,
  SourceReviewInput,
  InstructionImportPreview,
  FeedbackCreate,
  FeedbackUpdate,
  FeedbackItem,
  FeedbackPage,
  FeedbackFilters,
} from "./types";
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
export async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  const response = await fetch(`/api${path}`, {
    ...options,
    headers,
    credentials: "include",
  });
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const b = await response.json();
      detail =
        typeof b.detail === "string" ? b.detail : JSON.stringify(b.detail ?? b);
    } catch {
      /* keep status */
    }
    throw new ApiError(detail, response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
const post = <T>(path: string, body: unknown = {}) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body) });
const patch = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "PATCH", body: JSON.stringify(body) });
const id = (s: string) => encodeURIComponent(s);
const session = (s: string) => `/sessions/${id(s)}`;
export type UploadProgress = {
  loaded: number;
  total: number | null;
  complete: boolean;
};
export function uploadRequest<T>(
  path: string,
  body: FormData,
  progress: (value: UploadProgress) => void,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    let current: UploadProgress = { loaded: 0, total: null, complete: false };
    xhr.open("POST", `/api${path}`);
    xhr.withCredentials = true;
    xhr.responseType = "json";
    xhr.upload.onprogress = (event) => {
      current = {
        loaded: event.loaded,
        total: event.lengthComputable ? event.total : null,
        complete: false,
      };
      progress(current);
    };
    xhr.upload.onload = () => {
      current = { ...current, complete: true };
      progress(current);
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(xhr.response as T);
      else {
        const detail = xhr.response?.detail;
        reject(
          new ApiError(
            typeof detail === "string"
              ? detail
              : detail
                ? JSON.stringify(detail)
                : `Upload failed (${xhr.status})`,
            xhr.status,
          ),
        );
      }
    };
    xhr.onerror = () =>
      reject(
        new ApiError(
          "Upload connection lost. Check the course library before retrying this file.",
          0,
        ),
      );
    xhr.onabort = () =>
      reject(
        new ApiError(
          "Upload interrupted. Check the course library before retrying this file.",
          0,
        ),
      );
    progress(current);
    xhr.send(body);
  });
}
export const versionQuery = (version?: string | null) =>
  version == null ? "" : `?version_id=${id(version)}`;
const previewQuery = (version?: string | null, previewId?: string) => {
  const query = versionQuery(version);
  return (
    query + (previewId ? `${query ? "&" : "?"}preview_id=${id(previewId)}` : "")
  );
};
const roster = (cid?: string) =>
  cid ? `/teacher/courses/${id(cid)}/students` : "/admin/students";
const versions = (cid: string) => `/teacher/courses/${id(cid)}/versions`;
export const api = {
  liveConnection: (signal?: AbortSignal) =>
    request<LiveConnection>("/ai/connection", { signal }),
  accessSettings: () => request<AccessSettings>("/admin/access-settings"),
  saveAccessSettings: (body: AccessSettings) =>
    request<AccessSettings>("/admin/access-settings", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  history: () => request<LearningRun[]>("/history"),
  bootstrap: () => request<Bootstrap>("/bootstrap"),
  me: () => request<{ user: User }>("/auth/me"),
  demo: (role: Role, student_index: 1 | 2 = 1) =>
    post<{ user: User }>("/auth/demo", { role, student_index }),
  login: (email: string, password: string) =>
    post<{ user: User }>("/auth/login", { email, password }),
  register: (
    name: string,
    email: string,
    password: string,
    join_code: string,
  ) =>
    post<{ user: User }>("/auth/register", {
      name,
      email,
      password,
      join_code,
    }),
  logout: () => post<{ ok: true }>("/auth/logout"),
  profile: (name: string) => patch<{ user: User }>("/auth/profile", { name }),
  uploadAvatar: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<{ user: User }>("/auth/avatar", { method: "POST", body });
  },
  removeAvatar: () =>
    request<{ user: User }>("/auth/avatar", { method: "DELETE" }),
  feedbackCreate: (payload: FeedbackCreate) =>
    post<FeedbackItem>("/feedback", payload),
  feedbackList: (filters: FeedbackFilters = {}, admin = false) => {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(filters))
      if (value !== undefined) query.set(key, String(value));
    const suffix = query.size ? `?${query.toString()}` : "";
    return request<FeedbackPage>(`${admin ? "/admin" : ""}/feedback${suffix}`);
  },
  feedbackGet: (feedbackId: string, admin = false) =>
    request<FeedbackItem>(
      `${admin ? "/admin" : ""}/feedback/${id(feedbackId)}`,
    ),
  feedbackByRequest: (requestId: string) =>
    request<FeedbackItem>(`/feedback/requests/${id(requestId)}`),
  feedbackUpdate: (feedbackId: string, payload: FeedbackUpdate) =>
    patch<FeedbackItem>(`/admin/feedback/${id(feedbackId)}`, payload),
  changePassword: (current_password: string, new_password: string) =>
    post<{ user: User }>("/auth/change-password", {
      current_password,
      new_password,
    }),
  provisionStudent: (
    course_id: string,
    body: { name: string; email: string; temporary_password: string },
  ) => post<{ user: User; course_id: string }>(roster(course_id), body),
  teachers: () => request<User[]>("/admin/teachers"),
  promoteTeacher: (uid: string) =>
    post<{ user: User }>(`/admin/teachers/${id(uid)}/promote`),
  roster: (cid?: string, archived = false) =>
    request<RosterEntry[]>(`${roster(cid)}?archived=${archived}`),
  rosterAction: (
    action: "archive" | "restore",
    user_ids: string[],
    cid?: string,
  ) =>
    post<{ affected_ids: string[] }>(`${roster(cid)}/${action}`, { user_ids }),
  rosterPreview: (cid: string, file: File, password: string) => {
    const body = new FormData();
    body.set("file", file);
    if (password) body.set("default_temporary_password", password);
    return request<RosterPreview>(`${roster(cid)}/import/preview`, {
      method: "POST",
      body,
    });
  },
  rosterCommit: (cid: string, import_id: string) =>
    post<RosterResult>(`${roster(cid)}/import/${id(import_id)}/commit`),
  courses: () => request<Course[]>("/courses"),
  courseDetails: (cid: string) => request<CourseDetails>(`/courses/${id(cid)}`),
  updateCourse: (cid: string, body: CoursePatch) =>
    patch<CourseDetails>(`/courses/${id(cid)}`, body),
  courseTrash: () => request<{ courses: CourseDetails[] }>("/courses/trash"),
  trashCourse: (cid: string) =>
    post<CourseDetails>(`/courses/${id(cid)}/trash`, {}),
  restoreCourse: (cid: string) =>
    post<CourseDetails>(`/courses/${id(cid)}/restore`, {}),
  createCourse: (title: string, code: string, description: string) =>
    post<Course>("/courses", { title, code, description }),
  joinCourse: (join_code: string) =>
    post<Course>("/courses/join", { join_code }),
  sessions: (cid: string) =>
    request<SessionSummary[]>(`/courses/${id(cid)}/sessions`),
  deletedSessions: (cid: string) =>
    request<{ sessions: (SessionSummary & { removed_at: string })[] }>(
      `/courses/${id(cid)}/sessions/trash`,
    ),
  deleteSession: (sid: string) =>
    request<{ id: string; removed: boolean }>(session(sid), {
      method: "DELETE",
    }),
  restoreSession: (sid: string) =>
    post<{ id: string; restored: boolean }>(`${session(sid)}/restore`),
  createSession: (cid: string, title: string, number: number, subtitle = "") =>
    post<SessionDetail>(`/courses/${id(cid)}/sessions`, {
      title,
      number,
      subtitle,
      instructions: "",
      learning_objectives: [],
    }),
  session: (sid: string) => request<SessionDetail>(session(sid)),
  updateSession: (sid: string, body: SessionPatch) =>
    patch<SessionDetail>(session(sid), body),
  teachingPreview: (sid: string, body: TeachingPreviewInput) =>
    post<TeachingPreview>(`${session(sid)}/teaching-preview`, body),
  previewInfo: (sid: string) =>
    request<PreviewInfo>(`/teacher${session(sid)}/preview`),
  resetPreview: (sid: string, expected_revision: string) =>
    post<Workspace>(`/teacher${session(sid)}/preview/reset`, {
      expected_revision,
    }),
  sourceReview: (sid: string, body: SourceReviewInput) =>
    post<SourceReview>(`/teacher${session(sid)}/source-review`, body),
  instructionPreview: (sid: string, file: File) => {
    const body = new FormData();
    body.set("file", file);
    return request<InstructionImportPreview>(
      `/teacher${session(sid)}/instruction-import/preview`,
      { method: "POST", body },
    );
  },
  tutorStart: (
    sid: string,
    request_id?: string,
    vid?: string | null,
    preview_id?: string,
  ) =>
    post<Workspace>(`${session(sid)}/tutor/start${versionQuery(vid)}`, {
      request_id,
      ...(preview_id ? { preview_id } : {}),
    }),
  tutorTurn: (sid: string, body: TutorTurn, vid?: string | null) =>
    post<Workspace>(`${session(sid)}/tutor/turn${versionQuery(vid)}`, body),
  transcriptUrl: (sid: string, format: "html" | "txt", vid?: string | null) => {
    const query = versionQuery(vid);
    return `/api${session(sid)}/transcript${query}${query ? "&" : "?"}format=${format}`;
  },
  workspace: (sid: string, vid?: string | null) =>
    request<Workspace>(`${session(sid)}/workspace${versionQuery(vid)}`),
  reading: (
    sid: string,
    group_id: string,
    vid?: string | null,
    previewId?: string,
  ) =>
    post<Workspace>(`${session(sid)}/reading${previewQuery(vid, previewId)}`, {
      group_id,
    }),
  answer: (
    sid: string,
    qid: string,
    answer: string,
    vid?: string | null,
    previewId?: string,
  ) =>
    post<Workspace>(
      `${session(sid)}/answers/${id(qid)}${previewQuery(vid, previewId)}`,
      {
        answer,
      },
    ),
  chat: (
    sid: string,
    message: string,
    question_id: string | null,
    intent: "answer" | "ask",
    request_id?: string,
    web_search = false,
    vid?: string | null,
  ) =>
    post<Workspace>(`${session(sid)}/chat${versionQuery(vid)}`, {
      message,
      question_id,
      intent,
      request_id,
      web_search,
    }),
  reference: (
    sid: string,
    qid: string,
    vid?: string | null,
    previewId?: string,
  ) =>
    post<Reference>(
      `${session(sid)}/references/${id(qid)}${previewQuery(vid, previewId)}`,
    ),
  readReference: (sid: string, qid: string, vid?: string | null) =>
    request<Reference>(
      `${session(sid)}/references/${id(qid)}${versionQuery(vid)}`,
    ),
  submit: (sid: string, vid?: string | null, previewId?: string) =>
    post<Workspace>(`${session(sid)}/submit${previewQuery(vid, previewId)}`),
  students: (sid: string, vid?: string | null) =>
    request<StudentRow[]>(
      `/teacher/sessions/${id(sid)}/students${versionQuery(vid)}`,
    ),
  studentWorkspace: (sid: string, uid: string, vid?: string | null) =>
    request<Workspace>(
      `/teacher/sessions/${id(sid)}/students/${id(uid)}/workspace${versionQuery(vid)}`,
    ),
  review: (
    sid: string,
    uid: string,
    status: "confirmed" | "needs_revision",
    note: string,
    vid?: string | null,
  ) =>
    post<Workspace>(
      `/teacher/sessions/${id(sid)}/students/${id(uid)}/review${versionQuery(vid)}`,
      { status, note },
    ),
  upload: (
    sid: string,
    file: File,
    visibility: "student" | "teacher",
    kind: string,
    processing?: "preview" | "full_document",
    onProgress?: (value: UploadProgress) => void,
  ) => {
    const body = new FormData();
    body.set("file", file);
    body.set("visibility", visibility);
    body.set("kind", kind);
    if (processing !== undefined) body.set("processing", processing);
    if (onProgress)
      return uploadRequest<Material>(
        `${session(sid)}/materials`,
        body,
        onProgress,
      );
    return request<Material>(`${session(sid)}/materials`, {
      method: "POST",
      body,
    });
  },
  courseMaterials: (cid: string) =>
    request<{ materials: CourseMaterial[] }>(`/courses/${id(cid)}/materials`),
  attachMaterial: (sid: string, material_id: string) =>
    post<Material>(`${session(sid)}/materials/attach`, { material_id }),
  reprocessMaterial: (sid: string, mid: string) =>
    post<Material>(`${session(sid)}/materials/${id(mid)}/reprocess`),
  createLink: (
    sid: string,
    body: { url: string; title?: string; visibility: "student" | "teacher" },
  ) => post<Material>(`${session(sid)}/materials/link`, body),
  updateMaterial: (
    sid: string,
    mid: string,
    body: {
      title?: string;
      kind?: string;
      visibility?: "student" | "teacher";
      url?: string;
    },
  ) => patch<Material>(`${session(sid)}/materials/${id(mid)}`, body),
  archiveMaterial: (sid: string, mid: string) =>
    request<unknown>(`${session(sid)}/materials/${id(mid)}`, {
      method: "DELETE",
    }),
  previewUrl: (mid: string, vid?: string | null) =>
    `/api/materials/${id(mid)}/preview${versionQuery(vid)}`,
  worksheetFromMaterial: (
    sid: string,
    material_id: string,
    answer_material_id: string | null,
    use_ai = true,
  ) =>
    request<WorksheetPreview>(
      `${session(sid)}/worksheet-import/from-material`,
      {
        method: "POST",
        body: JSON.stringify({ material_id, answer_material_id, use_ai }),
      },
    ),
  worksheetPreview: (sid: string, file: File, use_ai: boolean) => {
    const body = new FormData();
    body.set("file", file);
    body.set("use_ai", String(use_ai));
    return request<WorksheetPreview>(
      `${session(sid)}/worksheet-import/preview`,
      { method: "POST", body },
    );
  },
  worksheetCommit: (
    sid: string,
    iid: string,
    draft: WorksheetDraft,
    mode: "append" | "replace",
  ) =>
    post<SessionDetail>(`${session(sid)}/worksheet-import/${id(iid)}/commit`, {
      groups: draft.groups,
      questions: draft.questions,
      reference_answers: draft.reference_answers,
      mode,
    }),
  versions: (cid: string) => request<VersionList>(versions(cid)),
  publishVersion: (cid: string, label: string) =>
    post<VersionEntry>(`${versions(cid)}/publish`, { label }),
  version: (cid: string, vid: string) =>
    request<VersionSnapshot>(`${versions(cid)}/${id(vid)}`),
  versionDiff: (cid: string, vid: string) =>
    request<VersionDiff>(`${versions(cid)}/${id(vid)}/diff`),
  restoreVersion: (cid: string, vid: string, label: string) =>
    post<VersionEntry>(`${versions(cid)}/${id(vid)}/restore`, { label }),
  searchSettings: () => request<SearchSettings>("/teacher/search-settings"),
  saveSearchSettings: (body: SearchSettingsPatch) =>
    request<SearchSettings>("/teacher/search-settings", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  testSearchSettings: () =>
    post<{
      ok: boolean;
      message: string;
      connection: ConnectionCheck;
      result_count: number;
    }>("/teacher/search-settings/test"),
  settings: () => request<Settings>("/teacher/settings"),
  saveSettings: (
    body: Pick<AiStatus, "mode" | "base_url" | "model"> & { api_key?: string },
  ) =>
    request<Settings>("/teacher/settings", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  testSettings: () =>
    post<{ ok: boolean; message: string; model: string; mode: string }>(
      "/teacher/settings/test",
    ),
  exportUrl: (sid: string, uid?: string, vid?: string | null) =>
    (uid
      ? `/api/teacher/sessions/${id(sid)}/students/${id(uid)}/export`
      : `/api${session(sid)}/export`) + versionQuery(vid),
};
