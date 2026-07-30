/**
 * Vihara's API client (D1 §5, VP-01 consumer).
 *
 * The auth contract is the shipped one — bearer access token, refresh on
 * 401 — but the *storage* is not: the access token lives in a module
 * variable and nowhere else, and the refresh token never reaches this code
 * at all (it rides an HttpOnly cookie the server set in cookie mode). A
 * test pins that no storage API appears anywhere under src/ — an XSS on
 * the app that renders generated UI must have nothing durable to steal.
 */
import axios, { AxiosError, type AxiosInstance } from "axios";

let accessToken: string | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

/** The readable half of the CSRF double-submit (the cookie is deliberately
 * not HttpOnly — being able to read it is what proves same-origin). */
export function csrfFromCookie(cookieHeader: string): string | null {
  for (const part of cookieHeader.split(";")) {
    const [name, ...rest] = part.trim().split("=");
    if (name === "csrf_token") return rest.join("=") || null;
  }
  return null;
}

export const api: AxiosInstance = axios.create({
  baseURL: "/api/v1",
  withCredentials: true,
});

api.interceptors.request.use((config) => {
  if (accessToken !== null) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

let refreshing: Promise<boolean> | null = null;

/** Refresh via the cookie path: the browser sends the HttpOnly refresh
 * cookie; we echo the CSRF cookie in the header. Returns whether a new
 * access token was obtained. Never throws — a failed refresh is a normal
 * logged-out state, not an error cascade. */
export async function refreshAccessToken(): Promise<boolean> {
  refreshing ??= (async () => {
    try {
      const csrf = csrfFromCookie(document.cookie);
      const response = await axios.post<{ access_token: string }>(
        "/api/v1/auth/refresh",
        null,
        {
          withCredentials: true,
          headers: {
            "X-Token-Delivery": "cookie",
            ...(csrf !== null ? { "X-CSRF-Token": csrf } : {}),
          },
        },
      );
      setAccessToken(response.data.access_token);
      return true;
    } catch {
      setAccessToken(null);
      return false;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

api.interceptors.response.use(undefined, async (error: AxiosError) => {
  const original = error.config;
  if (
    error.response?.status === 401 &&
    original !== undefined &&
    (original as { _retried?: boolean })._retried !== true
  ) {
    (original as { _retried?: boolean })._retried = true;
    if (await refreshAccessToken()) {
      return api.request(original);
    }
  }
  throw error;
});

export interface Credentials {
  email: string;
  password: string;
}

export async function login(credentials: Credentials): Promise<void> {
  const response = await api.post<{ access_token: string }>(
    "/auth/login",
    credentials,
    { headers: { "X-Token-Delivery": "cookie" } },
  );
  setAccessToken(response.data.access_token);
}

export async function register(body: {
  email: string;
  password: string;
  full_name: string;
  company_name?: string;
}): Promise<void> {
  const response = await api.post<{ access_token: string }>(
    "/auth/register",
    body,
    { headers: { "X-Token-Delivery": "cookie" } },
  );
  setAccessToken(response.data.access_token);
}

export function logout(): void {
  setAccessToken(null);
}
