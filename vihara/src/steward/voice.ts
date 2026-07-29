/**
 * Voice on the client (STEWARD S8): mic capture to PCM16 frames, a
 * playback queue for her 24 kHz PCM, and the local VAD that makes
 * barge-in client-side (the design's call: a browser is not a dumb pipe,
 * so the phone leg's server VAD is not needed here).
 *
 * The pure parts — sample conversion, RMS — are exported and tested; the
 * browser-API parts guard their absence and are injected in dock tests.
 * Echo cancellation is getUserMedia's job (`echoCancellation: true`), not
 * ours.
 */

export const MIC_SAMPLE_RATE = 16000;
export const PLAYBACK_SAMPLE_RATE = 24000;

/** Float32 [-1, 1] → little-endian PCM16 bytes (what the ASR expects). */
export function floatTo16BitPCM(samples: Float32Array): ArrayBuffer {
  const out = new ArrayBuffer(samples.length * 2);
  const view = new DataView(out);
  for (let i = 0; i < samples.length; i += 1) {
    const clamped = Math.max(-1, Math.min(1, samples[i] ?? 0));
    view.setInt16(i * 2, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
  }
  return out;
}

/** Little-endian PCM16 bytes → Float32 [-1, 1] (what WebAudio plays). */
export function pcm16ToFloat32(buffer: ArrayBuffer): Float32Array {
  const view = new DataView(buffer);
  const length = Math.floor(buffer.byteLength / 2);
  const out = new Float32Array(length);
  for (let i = 0; i < length; i += 1) {
    const sample = view.getInt16(i * 2, true);
    out[i] = sample < 0 ? sample / 0x8000 : sample / 0x7fff;
  }
  return out;
}

/** Root-mean-square level of a frame — the local VAD's one number. */
export function rmsLevel(samples: Float32Array): number {
  if (samples.length === 0) return 0;
  let sum = 0;
  for (const sample of samples) sum += sample * sample;
  return Math.sqrt(sum / samples.length);
}

/** Above this RMS the human is talking. Tuned against normal speech at a
 * normal mic gain; a threshold too low makes every keyboard clack a
 * barge-in, too high makes her untalk-over-able. */
export const VAD_RMS_THRESHOLD = 0.02;

export interface MicCapture {
  stop(): void;
}

export interface MicHandlers {
  onFrame: (frame: ArrayBuffer) => void;
  /** Fired when the human's level crosses the VAD threshold. */
  onSpeech?: () => void;
}

/**
 * Capture the mic as PCM16 frames at 16 kHz. Returns null where the
 * browser APIs are absent (jsdom, denied permission) — the dock renders
 * the mic as unavailable rather than broken.
 */
export async function createMicCapture(
  handlers: MicHandlers,
): Promise<MicCapture | null> {
  const media = globalThis.navigator?.mediaDevices;
  const AudioContextCtor = (globalThis as { AudioContext?: typeof AudioContext })
    .AudioContext;
  if (media === undefined || AudioContextCtor === undefined) return null;
  try {
    const stream = await media.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true },
    });
    const context = new AudioContextCtor({ sampleRate: MIC_SAMPLE_RATE });
    const source = context.createMediaStreamSource(stream);
    const processor = context.createScriptProcessor(4096, 1, 1);
    processor.onaudioprocess = (event) => {
      const samples = event.inputBuffer.getChannelData(0);
      if (handlers.onSpeech && rmsLevel(samples) > VAD_RMS_THRESHOLD) {
        handlers.onSpeech();
      }
      handlers.onFrame(floatTo16BitPCM(samples));
    };
    source.connect(processor);
    processor.connect(context.destination);
    return {
      stop: () => {
        processor.disconnect();
        source.disconnect();
        for (const track of stream.getTracks()) track.stop();
        void context.close();
      },
    };
  } catch {
    return null;
  }
}

export interface PcmPlayer {
  enqueue(frame: ArrayBuffer): void;
  /** Barge-in: drop everything queued and go silent now. */
  stop(): void;
  close(): void;
}

/**
 * Sequentially schedule her PCM chunks. A cursor tracks where the last
 * chunk ends so frames butt-join without gaps; `stop()` moves the cursor
 * to now so nothing queued ever plays.
 */
export function createPcmPlayer(): PcmPlayer | null {
  const AudioContextCtor = (globalThis as { AudioContext?: typeof AudioContext })
    .AudioContext;
  if (AudioContextCtor === undefined) return null;
  const context = new AudioContextCtor();
  let cursor = 0;
  const playing = new Set<AudioBufferSourceNode>();
  return {
    enqueue: (frame) => {
      const samples = pcm16ToFloat32(frame);
      if (samples.length === 0) return;
      const buffer = context.createBuffer(
        1, samples.length, PLAYBACK_SAMPLE_RATE);
      buffer.copyToChannel(samples as Float32Array<ArrayBuffer>, 0);
      const node = context.createBufferSource();
      node.buffer = buffer;
      node.connect(context.destination);
      const at = Math.max(cursor, context.currentTime);
      node.start(at);
      cursor = at + buffer.duration;
      playing.add(node);
      node.onended = () => playing.delete(node);
    },
    stop: () => {
      for (const node of [...playing]) {
        try {
          node.stop();
        } catch {
          // Already ended.
        }
      }
      playing.clear();
      cursor = 0;
    },
    close: () => {
      void context.close();
    },
  };
}
