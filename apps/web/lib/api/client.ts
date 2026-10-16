"use client";

// Client API sinh từ OpenAPI (spec 05 §10). Mọi request gắn ID token Firebase và `X-Tenant-Id` của khách đang chọn.
// Web chỉ gọi services/api; không gọi Cube, BigQuery hay Postgres trực tiếp.
import createClient, { type Middleware } from "openapi-fetch";
import { idToken } from "@/lib/auth/firebase";
import { currentTenant } from "@/lib/tenant-store";
import type { paths } from "./schema";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Lỗi theo RFC 9457 mà API trả (spec 05 §9). */
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    public detail: string,
    public requestId?: string,
  ) {
    super(detail || code);
  }
}

const auth: Middleware = {
  async onRequest({ request }) {
    const token = await idToken();
    if (token) request.headers.set("Authorization", `Bearer ${token}`);
    const t = currentTenant();
    if (t && !request.headers.has("X-Tenant-Id")) request.headers.set("X-Tenant-Id", t);
    return request;
  },
};

export const api = createClient<paths>({ baseUrl: API_URL });
api.use(auth);

type Result<T> = { data?: T; error?: unknown; response: Response };

/** Trả `data` hoặc ném `ApiError` với thông điệp tiếng Việt của API. */
export async function unwrap<T>(p: Promise<Result<T>>): Promise<T> {
  const { data, error, response } = await p;
  if (response.ok) return data as T;
  const e = (error ?? {}) as { code?: string; detail?: unknown; title?: string; request_id?: string };
  const detail =
    typeof e.detail === "string"
      ? e.detail
      : Array.isArray(e.detail)
        ? "Dữ liệu gửi lên không hợp lệ"
        : (e.title ?? `Lỗi ${response.status}`);
  throw new ApiError(response.status, e.code ?? `HTTP_${response.status}`, detail, e.request_id);
}

/** Gọi đường dẫn không có trong schema (ví dụ tải file) với cùng header xác thực. */
export async function rawFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = await idToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const t = currentTenant();
  if (t) headers.set("X-Tenant-Id", t);
  return fetch(`${API_URL}${path}`, { ...init, headers });
}

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.detail;
  if (e instanceof Error) return e.message;
  return "Đã có lỗi, thử lại sau";
}
