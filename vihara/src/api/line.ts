/**
 * The Line's own reads (LINE L5–L9): the morning story and the push subscribe
 * flow over SEAM T7.
 *
 * The thread's history moved to `./pragya` (R-4 part P) — it reads
 * `/ai/pragya/history`, which is the conversation seam rather than the Line's,
 * and it now sits beside the turn endpoint the Brainstorm posts to. One path,
 * one wrapper.
 */
import { api } from "./client";

export interface MorningCard {
  entity_id: string;
  name: string;
  district: string;
  sentences: string[];
  waiting: boolean;
  audio: { mime: string; data_b64: string } | null;
}

export interface MorningStory {
  story_date: string;
  cards: MorningCard[];
  generated_at: string | null;
  degraded_reason: string | null;
}

export async function fetchMorningStory(): Promise<MorningStory> {
  return (await api.get<MorningStory>("/ai/genui/line/morning")).data;
}

export async function fetchVapidKey(): Promise<string | null> {
  const { data } = await api.get<{ key: string | null; configured: boolean }>(
    "/ai/genui/push/vapid-public-key",
  );
  return data.configured ? data.key : null;
}

export async function registerPushSubscription(subscription: {
  endpoint: string;
  keys: { p256dh: string; auth: string };
  ua?: string;
}): Promise<void> {
  await api.post("/ai/genui/push/subscriptions", subscription);
}
