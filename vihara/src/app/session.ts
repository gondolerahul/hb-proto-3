import { logout } from "../api/client";

/**
 * The one door out of a session (R-4 §3, A3/A4).
 *
 * Ending a session is two facts — the client must forget the access token, and
 * the app must stop rendering the estate — and they live in different layers.
 * A DOM event is the join, chosen over an exported setter because the *other*
 * caller is `api/client.ts`'s 401 path: a module below the app, which must not
 * import upward to tell it something happened. Anything that discovers the
 * session is over dispatches this and is done.
 *
 * **The two endings are different events, because they mean different things.**
 * `"left"` is a person choosing to go, and it forgets where they were — a shared
 * machine should not announce which room the last user was in. `"expired"` is
 * the session running out underneath them, and it keeps the place so that
 * logging back in resumes rather than restarts (A4).
 *
 * There is no storage here and nothing to clear. VP-01 puts the access token in
 * a module variable, the refresh token in an HttpOnly cookie, and nothing
 * anywhere else — so "log out" on this client is genuinely: drop one variable,
 * and let the cookie be cleared or expire server-side.
 */
export const SESSION_ENDED = "vihara:session-ended";

export type SessionEnding = "left" | "expired";

export function endSession(how: SessionEnding = "expired"): void {
  logout();
  window.dispatchEvent(new CustomEvent<SessionEnding>(SESSION_ENDED, { detail: how }));
}
