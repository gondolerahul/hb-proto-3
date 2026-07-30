/**
 * The Study — the desk you sit at (D6 §15a).
 *
 * Bound to `/auth/me`, `/ai/authn/status` + `/ai/authn/webauthn/credentials`,
 * `/ai/learning/preferences` (`notify.*`, `density.*`) + `observe-density`, and
 * `/credits/balance` + `/credits/subscriptions`.
 */

export interface Passkey {
  id: string;
  label: string;
  addedOn: string;
  /** The device you are on now — deleting it is the one with a consequence. */
  thisDevice: boolean;
  lastUsed: string;
}

export interface NotifyPref {
  key: string;
  label: string;
  detail: string;
  on: boolean;
}

/** The dunning ladder, in the order it is climbed. */
export interface DunningRung {
  state: "notify" | "grace" | "read-only" | "suspended";
  label: string;
  what: string;
}

export const YOU = {
  name: "Rahul",
  email: "rahul@northwind.co",
  company: "Northwind Textiles",
  role: "Owner",
  since: "12 March 2026",
};

export const PASSKEYS: Passkey[] = [
  { id: "pk-1", label: "MacBook Touch ID", addedOn: "12 March 2026", thisDevice: true, lastUsed: "34 minutes ago" },
  { id: "pk-2", label: "Pixel 9", addedOn: "2 June 2026", thisDevice: false, lastUsed: "yesterday" },
];

export const DENSITY = {
  /** What the owner has stated. `null` means they have never stated one. */
  stated: null as "novice" | "operator" | null,
  /** What LEARN has observed. Shown beside the switch, never hidden. */
  learned: "novice" as "novice" | "operator",
  observations: 4,
};

export const NOTIFY: NotifyPref[] = [
  {
    key: "notify.push.device",
    label: "Push on this device",
    detail: "Only when a colleague raises a hand. Never for anything you can read later.",
    on: true,
  },
  {
    key: "notify.morning.story",
    label: "The morning story",
    detail: "One message at 08:00, the standup in ninety seconds. Turning it off does not silence hands raised.",
    on: true,
  },
  {
    key: "notify.whatsapp.mirror",
    label: "WhatsApp as a last resort",
    detail: "Used only if push has failed twice and something is waiting on you.",
    on: false,
  },
];

export const WALLET = {
  balanceINR: 4_200,
  plan: "Growth",
  /** `current` | `grace` | `read-only` | `suspended` — drives the whole panel. */
  state: "current" as DunningRung["state"] | "current",
  renewsOn: "1 September 2026",
  lastTopUp: { on: "1 August 2026", amountINR: 10_000 },
  /** Burn over the trailing week, so "how long do I have" is answerable. */
  weeklyBurnINR: 1_150,
};

/**
 * The ladder, stated in words.
 *
 * The Study is the **one** surface that must explain why the estate has gone
 * quiet, because everywhere else quiet reads as calm — which is the whole design
 * of the product working against the tenant at the worst possible moment. So the
 * rungs are always visible, not only once one is reached: a tenant who is
 * current can see what would happen, and a tenant in `read-only` sees where they
 * are on a ladder they had already been shown.
 */
export const DUNNING: DunningRung[] = [
  {
    state: "notify",
    label: "We tell you",
    what: "A card in your tray and one message. Nothing changes about how the estate runs.",
  },
  {
    state: "grace",
    label: "Seven days of grace",
    what: "Everything keeps running. We stop starting anything new that costs money.",
  },
  {
    state: "read-only",
    label: "The estate goes quiet",
    what: "Your colleagues stop acting and keep watching. Nothing is deleted, nothing is lost, and the record stays complete. You can still read everything.",
  },
  {
    state: "suspended",
    label: "Suspended",
    what: "Access pauses. Your data is kept, and a full export stays available to you for ninety days.",
  },
];
