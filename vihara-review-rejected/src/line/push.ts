/**
 * The push client (LINE L9) — the subscribe flow over SEAM T7, and the
 * honest iOS answer computed BEFORE the user hunts for a prompt that
 * will never come: on iOS, push exists only after the PWA is installed
 * (the exit demo's "demonstrated rather than discovered").
 */
import { fetchVapidKey, registerPushSubscription } from "../api/line";

export type PushAvailability =
  | { state: "ready" }
  | { state: "subscribed" }
  | { state: "needs-install-first" }
  | { state: "unsupported" }
  | { state: "unconfigured" };

export function isStandalone(): boolean {
  return (
    window.matchMedia?.("(display-mode: standalone)").matches === true ||
    (navigator as { standalone?: boolean }).standalone === true
  );
}

export function isIos(): boolean {
  return /iphone|ipad|ipod/i.test(navigator.userAgent);
}

/** base64url VAPID key → the Uint8Array PushManager wants. */
export function vapidKeyBytes(key: string): Uint8Array {
  const padded = key + "=".repeat((4 - (key.length % 4)) % 4);
  const raw = atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (char) => char.charCodeAt(0));
}

export async function pushAvailability(): Promise<PushAvailability> {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    if (isIos() && !isStandalone()) return { state: "needs-install-first" };
    return { state: "unsupported" };
  }
  if (isIos() && !isStandalone()) return { state: "needs-install-first" };
  const registration = await navigator.serviceWorker.ready;
  const existing = await registration.pushManager.getSubscription();
  if (existing !== null) return { state: "subscribed" };
  return { state: "ready" };
}

export async function subscribeToPush(): Promise<boolean> {
  const key = await fetchVapidKey();
  if (key === null) return false;
  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: vapidKeyBytes(key) as BufferSource,
  });
  const json = subscription.toJSON();
  if (!json.endpoint || !json.keys) return false;
  await registerPushSubscription({
    endpoint: json.endpoint,
    keys: { p256dh: json.keys["p256dh"] ?? "", auth: json.keys["auth"] ?? "" },
    ua: navigator.userAgent.slice(0, 250),
  });
  return true;
}
