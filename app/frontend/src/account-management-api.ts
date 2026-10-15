import { request } from "./api";
import type { Role, User } from "./types";
import type {
  AccountCreate,
  AccountDetail,
  AccountFilters,
  AccountImportPreview,
  AccountImportResult,
  AccountImportState,
  AccountPage,
  CourseBrief,
  GlobalAccount,
  StaffResponse,
} from "./account-management-types";
const id = encodeURIComponent;
const write = <T>(path: string, method: string, body?: unknown) =>
  request<T>(path, {
    method,
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
export const accountApi = {
  list: (filters: AccountFilters = {}) => {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(filters))
      if (v !== undefined && v !== "") q.set(k, String(v));
    return request<AccountPage>(`/admin/users${q.size ? `?${q}` : ""}`);
  },
  get: (uid: string) => request<AccountDetail>(`/admin/users/${id(uid)}`),
  create: (body: AccountCreate) =>
    write<{ user: User }>("/admin/users", "POST", body),
  role: (uid: string, role: Role) =>
    write<{ user: User }>(`/admin/users/${id(uid)}`, "PATCH", { role }),
  status: (uid: string, active: boolean) =>
    write<GlobalAccount>(`/admin/users/${id(uid)}/status`, "PUT", { active }),
  preview: (file: File, role: Role, password: string) => {
    const body = new FormData();
    body.set("file", file);
    body.set("default_role", role);
    if (password) body.set("default_temporary_password", password);
    return request<AccountImportPreview>("/admin/users/import/preview", {
      method: "POST",
      body,
    });
  },
  commit: (iid: string) =>
    write<AccountImportResult>(
      `/admin/users/import/${id(iid)}/commit`,
      "POST",
      {},
    ),
  importState: (iid: string) =>
    request<AccountImportState>(`/admin/users/import/${id(iid)}`),
  courses: () => request<{ courses: CourseBrief[] }>("/admin/courses"),
  staff: (cid: string) => request<StaffResponse>(`/courses/${id(cid)}/staff`),
  addStaff: (cid: string, uid: string) =>
    write<StaffResponse>(`/courses/${id(cid)}/staff`, "POST", { user_id: uid }),
  removeStaff: (cid: string, uid: string) =>
    write<StaffResponse>(`/courses/${id(cid)}/staff/${id(uid)}`, "DELETE"),
  primary: (cid: string, uid: string) =>
    write<StaffResponse>(`/courses/${id(cid)}/staff/primary`, "PUT", {
      user_id: uid,
    }),
};
