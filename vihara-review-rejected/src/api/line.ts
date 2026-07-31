/**
 * The Line's own reads (LINE L5–L9): the morning story, the thread's
 * history, and the push subscribe flow over SEAM T7.
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

export interface ThreadTurn {
  role: string;
  content: string;
  at: string;
}

export async function fetchThreadHistory(): Promise<ThreadTurn[]> {
  const { data } = await api.get<ThreadTurn[]>("/ai/pragya/history");
  return data;
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
