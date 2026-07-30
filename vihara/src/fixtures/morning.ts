/**
 * The Morning Story's data, shaped to `GET /ai/genui/line/morning` (LINE L1).
 *
 * The endpoint is `backend/src/ai/genui/morning.py`; the row it usually serves is
 * written at 02:25 UTC by `morning_job.py`. Field names are camel-cased to the
 * house convention and map one-to-one onto the wire's snake_case, so R-4 swaps
 * the source and not the surface (`story_date`, `entity_id`, `data_b64`,
 * `degraded_reason`).
 *
 * Two properties of this fixture are load-bearing rather than decorative.
 *
 * **The sentences are only the six the server can compose.** `compose_morning_story`
 * writes counts, not narrative — "Finished N pieces of work since yesterday.",
 * "One thing went wrong — it is in the trace.", "Is working on something right
 * now.", "Is waiting on you.", "A quiet day — nothing to report." — and nothing
 * else. Writing richer prose here would design a surface against a composition
 * the platform does not perform, which is the same class of error as inventing a
 * number. The counts themselves agree with the desk's `STANDUP` facts
 * (`fixtures/decisions.ts`) and the two waiting cards agree with
 * `STILL.handsRaised`, because morning.py's own docstring says it: if the phone
 * and the desk drift, they disagree about yesterday.
 *
 * **The degradation is the mid-story one.** `_synthesize` fills clips in order
 * and returns `"tts_failed"` on the first exception, keeping what it already
 * made — so a real broken morning is two voiced cards and three text ones, not a
 * silent story. That is the shape most worth designing against, because it is
 * the one where a surface can quietly pretend nothing is missing.
 */

/** Gemini's native rate, mirrored from `morning_job.WAV_SAMPLE_RATE`. A wrong
 *  value here does not raise — it plays at the wrong speed. */
const SAMPLE_RATE = 24000;

export interface MorningAudio {
  mime: string;
  /** Base64 of a RIFF/WAVE payload — `morning_job.wav_wrap` around 16-bit mono PCM. */
  dataB64: string;
}

export interface MorningCard {
  entityId: string;
  name: string;
  /** The district's process code, which is all the endpoint sends: `P08`. */
  district: string;
  /** Her telling, one sentence per composed fact. The clip says these joined. */
  sentences: string[];
  waiting: boolean;
  /** `null` where the job never made a clip for this card. Never a broken src. */
  audio: MorningAudio | null;
}

/** The four the job can record. A row may also be clean and a card still silent
 *  — see `MorningStorySurface`, which has a sentence for that too. */
export type DegradedReason = "wallet" | "not_configured" | "tts_failed" | "not_generated";

export interface MorningStory {
  /** A calendar date, not an instant. */
  storyDate: string;
  cards: MorningCard[];
  /** When the telling was made. `null` means the job has not run and this was
   *  composed on read — a different morning, honestly labelled. */
  generatedAt: string | null;
  degradedReason: DegradedReason | null;
}

/* ------------------------------------------------------------------ the clip
   A stand-in for her voice until R-4 wires the endpoint.

   It is synthesised rather than pasted in as base64 for two reasons. A real WAV
   is ~50 KB per card, and a literal that size in a source file is fifty
   kilobytes nobody will ever read again. More importantly, the alternative was a
   silent or absent `src` — and a play button that does nothing is exactly the
   lie this surface exists to refuse. The bytes are made the same way the job
   makes them, so the client's reader and the server's writer agree on the
   format before either is wired. */

function base64(bytes: Uint8Array): string {
  let binary = "";
  // 8 KB at a time: spreading a 50 KB array into fromCharCode overflows the
  // argument stack on some engines, and it does it silently until it does not.
  const CHUNK = 0x2000;
  for (let i = 0; i < bytes.length; i += CHUNK) {
    binary += String.fromCharCode(...bytes.subarray(i, i + CHUNK));
  }
  return btoa(binary);
}

/** The RIFF/WAVE header, byte for byte as `morning_job.wav_wrap` writes it. */
function wav(pcm: Int16Array): string {
  const bytes = new Uint8Array(44 + pcm.length * 2);
  const view = new DataView(bytes.buffer);
  const tag = (at: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(at + i, s.charCodeAt(i));
  };
  tag(0, "RIFF");
  view.setUint32(4, 36 + pcm.length * 2, true);
  tag(8, "WAVE");
  tag(12, "fmt ");
  view.setUint32(16, 16, true); // subchunk size
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, SAMPLE_RATE, true);
  view.setUint32(28, SAMPLE_RATE * 2, true); // byte rate
  view.setUint16(32, 2, true); // block align
  view.setUint16(34, 16, true); // bits per sample
  tag(36, "data");
  view.setUint32(40, pcm.length * 2, true);
  for (let i = 0; i < pcm.length; i++) view.setInt16(44 + i * 2, pcm[i]!, true);
  return base64(bytes);
}

/** A short warm tone, low and falling, with a soft attack and a long release —
 *  a placeholder that reads as a voice note rather than as an alert chime. */
function standInClip(step: number): MorningAudio {
  const seconds = 0.8;
  const n = Math.round(SAMPLE_RATE * seconds);
  const pcm = new Int16Array(n);
  const base = 132 + step * 9;
  for (let i = 0; i < n; i++) {
    const t = i / SAMPLE_RATE;
    const env = Math.min(1, t / 0.07) * Math.min(1, (seconds - t) / 0.3);
    const hz = base * (1 - t * 0.06);
    const wave =
      Math.sin(2 * Math.PI * hz * t) * 0.62 + Math.sin(4 * Math.PI * hz * t) * 0.2;
    pcm[i] = Math.round(wave * env * 8200);
  }
  return { mime: "audio/wav", dataB64: wav(pcm) };
}

/* ----------------------------------------------------------------- the story
   Thursday's morning, told at 02:25 UTC, with her voice lost after the second
   card. Whoever needs the owner comes first and quiet days come last, which is
   `compose_morning_story`'s sort and not a layout preference. */

export const MORNING: MorningStory = {
  storyDate: "2026-07-30",
  generatedAt: "2026-07-30T02:25:00.000Z",
  degradedReason: "tts_failed",
  cards: [
    {
      entityId: "AGT-046",
      name: "Meera",
      district: "P08",
      sentences: [
        "Finished 33 pieces of work since yesterday.",
        "One thing went wrong — it is in the trace.",
        "Is working on something right now.",
        "Is waiting on you.",
      ],
      waiting: true,
      audio: standInClip(0),
    },
    {
      entityId: "AGT-041",
      name: "Anjali",
      district: "P08",
      sentences: [
        "Finished 9 pieces of work since yesterday.",
        "Is waiting on you.",
      ],
      waiting: true,
      audio: standInClip(1),
    },
    {
      // The clip for this card is where synthesis raised. Everything from here
      // is text, and the surface says so on each card rather than once at the top.
      entityId: "AGT-038",
      name: "Ravi",
      district: "P08",
      sentences: [
        "Finished 16 pieces of work since yesterday.",
        "2 things went wrong — they are in the traces.",
        "Is working on something right now.",
      ],
      waiting: false,
      audio: null,
    },
    {
      // A colleague with nothing to report. The server has one sentence for
      // that and this is it — a thin card, honestly thin.
      entityId: "AGT-013",
      name: "Devika",
      district: "P03",
      sentences: ["A quiet day — nothing to report."],
      waiting: false,
      audio: null,
    },
    {
      entityId: "AGT-092",
      name: "Farhan",
      district: "P14",
      sentences: [
        "Finished 27 pieces of work since yesterday.",
        "Is working on something right now.",
      ],
      waiting: false,
      audio: null,
    },
  ],
};
