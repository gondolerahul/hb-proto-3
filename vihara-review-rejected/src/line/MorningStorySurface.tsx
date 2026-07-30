/**
 * The Morning Story (LINE L7, wireframes §16–18) — the Standup, swipeable,
 * her voice over each card. The audio is the job's pre-generated clip
 * (decision 2); a card without one plays nothing and shows its text —
 * and a degraded morning SAYS why (wallet, not configured), because a
 * story that silently lost its voice reads as a broken phone.
 */
import { useEffect, useRef, useState } from "react";

import { fetchMorningStory, type MorningStory } from "../api/line";
import { emitEcho } from "../api/genui";

export interface MorningLoaders {
  story: typeof fetchMorningStory;
  echo: typeof emitEcho;
}

const REAL: MorningLoaders = { story: fetchMorningStory, echo: emitEcho };

const DEGRADED_COPY: Record<string, string> = {
  wallet: "Text only this morning — the wallet could not cover her voice.",
  not_configured: "Text only — voice is not set up on this account yet.",
  tts_failed: "Text only past this point — her voice failed mid-story.",
  not_generated: "Composed just now — this morning's telling has not run yet.",
};

export function MorningStorySurface({
  loaders = REAL,
}: {
  loaders?: MorningLoaders;
}): JSX.Element {
  const [story, setStory] = useState<MorningStory | null>(null);
  const [failed, setFailed] = useState(false);
  const [index, setIndex] = useState(0);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const touchX = useRef<number | null>(null);

  useEffect(() => {
    let alive = true;
    void loaders
      .story()
      .then((data) => {
        if (alive) setStory(data);
      })
      .catch(() => {
        if (alive) setFailed(true);
      });
    return () => {
      alive = false;
    };
  }, [loaders]);

  if (failed) {
    return (
      <p role="alert" data-part="morning-failed">
        The morning could not be gathered.
      </p>
    );
  }
  if (story === null) {
    return <p className="vh-quiet">Gathering the morning…</p>;
  }
  if (story.cards.length === 0) {
    return (
      <p className="vh-quiet" data-part="morning-empty">
        No colleagues yet — the estate is still being built.
      </p>
    );
  }

  const card = story.cards[Math.min(index, story.cards.length - 1)];
  if (card === undefined) return <></>;
  const degraded =
    story.degraded_reason !== null
      ? DEGRADED_COPY[story.degraded_reason] ?? "Text only this morning."
      : null;

  const go = (next: number): void => {
    audioRef.current?.pause();
    const bounded = Math.max(0, Math.min(story.cards.length - 1, next));
    if (bounded !== index) {
      setIndex(bounded);
      void loaders.echo({
        sentence: `read ${story.cards[bounded]?.name ?? "a colleague"}'s morning card`,
        action_ref: {
          kind: "morning.swipe",
          surface_id: "line.morning",
          params: { index: bounded },
        },
      });
    }
  };

  return (
    <section
      data-part="morning-story"
      aria-label="Morning story"
      onTouchStart={(event) => {
        touchX.current = event.touches[0]?.clientX ?? null;
      }}
      onTouchEnd={(event) => {
        const start = touchX.current;
        touchX.current = null;
        const end = event.changedTouches[0]?.clientX;
        if (start === null || end === undefined) return;
        if (end - start > 48) go(index - 1);
        else if (start - end > 48) go(index + 1);
      }}
    >
      {degraded !== null && (
        <p className="vh-quiet" data-part="morning-degraded">
          {degraded}
        </p>
      )}
      <article className="vh-morning-card" data-part="morning-card">
        <header>
          <strong>{card.name}</strong>
          <span className="vh-quiet"> · {card.district}</span>
          {card.waiting && (
            <span className="vh-beacon-count" data-part="waiting-mark">
              waiting on you
            </span>
          )}
        </header>
        {card.sentences.map((sentence) => (
          <p key={sentence}>{sentence}</p>
        ))}
        {card.audio !== null && (
          <audio
            ref={audioRef}
            controls
            preload="none"
            data-part="card-audio"
            src={`data:${card.audio.mime};base64,${card.audio.data_b64}`}
          />
        )}
      </article>
      <nav className="vh-morning-nav" aria-label="story position">
        <button
          type="button"
          className="vh-quiet-link"
          disabled={index === 0}
          onClick={() => go(index - 1)}
        >
          ← previous
        </button>
        <span className="vh-quiet">
          {index + 1} of {story.cards.length}
        </span>
        <button
          type="button"
          className="vh-quiet-link"
          disabled={index === story.cards.length - 1}
          onClick={() => go(index + 1)}
        >
          next →
        </button>
      </nav>
    </section>
  );
}
