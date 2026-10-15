import type { Role, User } from "./types";
export type CourseBrief = {
  id: string;
  code: string;
  title: string;
  owner_id: string | null;
  trashed_at: string | null;
};
export type GlobalAccount = {
  user: User;
  active: boolean;
  archived_at: string | null;
  purge_at: string | null;
  assigned_course_count: number;
  owned_course_count: number;
};
export type AccountDetail = GlobalAccount & { staff_courses: CourseBrief[] };
export type AccountPage = {
  items: GlobalAccount[];
  total: number;
  offset: number;
  limit: number;
};
export type AccountFilters = {
  q?: string;
  role?: Role;
  active?: boolean;
  offset?: number;
  limit?: number;
};
export type AccountCreate = {
  name: string;
  email: string;
  role: Role;
  temporary_password: string;
};
export type AccountImportPreview = {
  import_id: string;
  rows: {
    row_number: number;
    name: string;
    email: string;
    role: Role;
    action: "create" | "skip" | "error";
    errors: string[];
    warnings: string[];
  }[];
  valid_count: number;
  error_count: number;
};
export type AccountImportResult = {
  created: number;
  skipped: number;
  user_ids: string[];
};
export type AccountImportState = {
  status: "pending" | "committed";
  preview: AccountImportPreview;
  result: AccountImportResult | null;
};
export type CourseStaffMember = {
  user: User;
  is_primary: boolean;
  active: boolean;
};
export type StaffResponse = { course: CourseBrief; staff: CourseStaffMember[] };
