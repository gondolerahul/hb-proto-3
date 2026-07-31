import { useState, type FormEvent } from "react";

import { Icon } from "../components/Icon";
import { reasonOf } from "../lifecycle";
import { sendTurn, type PragyaTurn } from "../api/pragya";
import { createRecord } from "../api/tenant";
import { grouped } from "./BoardroomSurface";
import "./brainstorm.css";

/**
 * Tabling a matter — the owner-initiated half of the Boardroom. Wired in R-4
 * part W to `POST /ai/pragya/chat` and `POST /ai/tenant/records`.
 *
 * **Owner review D (2026-07-30):** *"How do I brainstorm here — say I am thinking
 * about developing a new marketing plan?"* The honest answer was that there was
 * no way to. The Boardroom only rendered propositions raised from KPI drift; an
 * owner arriving with a thought had nowhere to put it.
 *
 * What closes the gap is deliberately **not a chat panel**. It is the front of
 * the same pipeline: a matter you table goes to Pragya's nine-stage runtime,
 * and what comes back can be filed as a **Proposition record** — which the
 * Boardroom then adopts into a Resolution by the same certified act as any
 * other. A second way to make strategy would defeat STRAT's whole premise,
 * which is that there is one.
 *
 * ## What the wiring removed, and why it is not a redesign
 *
 * The panel used to run a four-beat scripted exchange: she reads the matter
 * back, opens with figures she already holds, names what she cannot know, and
 * assembles a draft as you answer her questions. **`POST /ai/pragya/chat`
 * returns one `reply` string** and a set of flags about the turn. There is no
 * knows-list, no missing-list, no question set and no draft on the wire, and
 * §7.1 says a binding that cannot be answered renders nothing — so those four
 * blocks are gone rather than filled with something plausible.
 *
 * What replaced them is not decoration: it is **everything the turn actually
 * reports**, which the scripted version could not say at all. What it cost, the
 * stage it left the runtime on, whether it raised a card in your tray, what it
 * wrote, whom it delegated to, and whether it is waiting on you. Those are the
 * facts an owner needs to know a conversation had consequences.
 *
 * ## Three decisions
 *
 * 1. **`needs_step_up` and `needs_oob` are read, never re-derived, and never
 *    answered here.** The turn payload carries them because the client must be
 *    *told* a ceremony is due rather than inferring a tier it does not own.
 *    `useCertifiedAct` guards *acts*, not turns, so this panel says a ceremony
 *    is owed and says where it is taken — it does not open one it cannot
 *    complete.
 * 2. **The proposition is filed `untested`, and that is a rule rather than a
 *    default.** `check_honesty_grade` in `strategy/pipeline.py` refuses any
 *    grade without a `twin_run_id` behind it, so nothing simulated means
 *    nothing claimed. The Glasshouse is offered rather than a forecast implied.
 * 3. **A write is reported in the server's own vocabulary.** `WriteResult.status`
 *    can come back `proposed` rather than `written` when the Planning module is
 *    owned elsewhere — the change becomes a signal for its owner. Flattening
 *    that into "saved" would tell an owner their matter is on the record when
 *    it is a proposal waiting for somebody.
 *
 * The thread's history is deliberately not read here. It is one conversation
 * with one runtime, and the Line's Thread is where it is read back; rendering
 * the same turns in a boardroom panel would show the estate's owner two copies
 * of one exchange and let them drift.
 */

type Beat = "compose" | "replied";

/** What `createRecord` answered with, in the words the record service uses. */
type Filing =
  | { kind: "written"; id: string }
  | { kind: "proposed"; signalId: string | null }
  | { kind: "refused"; reason: string };

export function Brainstorm({
  onTabled,
  onEcho,
}: {
  /** A record landed, so the Boardroom's proposition list is stale. */
  onTabled: () => void;
  onEcho: (msg: string) => void;
}) {
  const [beat, setBeat] = useState<Beat>("compose");
  const [matter, setMatter] = useState("");
  const [turn, setTurn] = useState<PragyaTurn | null>(null);
  const [busy, setBusy] = useState(false);
  const [broke, setBroke] = useState<string | null>(null);
  const [filed, setFiled] = useState<Filing | null>(null);

  async function table(event: FormEvent): Promise<void> {
    event.preventDefault();
    const text = matter.trim();
    if (text === "" || busy) return;
    setBusy(true);
    setBroke(null);
    try {
      const answered = await sendTurn(text);
      setTurn(answered);
      setBeat("replied");
      onEcho(`tabled “${text}”`);
    } catch (thrown) {
      setBroke(reasonOf(thrown));
    } finally {
      setBusy(false);
    }
  }

  async function fileIt(): Promise<void> {
    const text = matter.trim();
    if (text === "" || turn === null || busy) return;
    setBusy(true);
    setBroke(null);
    try {
      const result = await createRecord("Proposition", {
        /* The owner's own words, unedited. A title this panel composed would
           be the estate paraphrasing the person it is meant to be listening
           to. */
        title: text,
        rationale: turn.reply,
        status: "tabled",
        /* Nothing has been simulated, so nothing may be claimed — and the
           pipeline refuses any other grade without a run behind it. */
        honesty_grade: "untested",
      });
      if (result.status === "written" && result.record !== null) {
        setFiled({ kind: "written", id: result.record.id });
        onEcho(`tabled ${text} as a proposition`);
        onTabled();
      } else if (result.status === "proposed") {
        setFiled({ kind: "proposed", signalId: result.signal_id });
        onEcho(`proposed ${text} as a proposition`);
        onTabled();
      } else {
        setFiled({
          kind: "refused",
          reason: result.reason ?? `The estate answered “${result.status}”.`,
        });
      }
    } catch (thrown) {
      setBroke(reasonOf(thrown));
    } finally {
      setBusy(false);
    }
  }

  function reset(): void {
    setBeat("compose");
    setMatter("");
    setTurn(null);
    setFiled(null);
    setBroke(null);
  }

  /* ------------------------------------------------------------- compose ---- */
  if (beat === "compose" || turn === null) {
    return (
      <section className="bs bs-compose m-plate" aria-label="Table a matter">
        <header className="bs-head">
          <span className="t-eyebrow">TABLE A MATTER</span>
          <p className="t-narrative bs-lead">
            Bring her something you are thinking about. She answers from the
            estate you actually have, and what comes back can be filed as a
            proposition this room can adopt.
          </p>
        </header>

        <form className="bs-form" onSubmit={(event) => void table(event)} aria-busy={busy}>
          <input
            className="bs-input"
            value={matter}
            onChange={(event) => setMatter(event.target.value)}
            placeholder="A marketing plan for the festive season…"
            aria-label="What would you like to table?"
          />
          <button className="m-btn" type="submit" disabled={busy || matter.trim() === ""}>
            <Icon name="forward" size={14} />
            Table it
          </button>
        </form>

        {broke !== null && (
          <p className="bs-broke" role="status">
            <span className="m-lamp" data-negative aria-hidden="true" />
            She did not answer, and nothing was recorded.
            <span className="bs-broke-reason t-mono">{broke}</span>
          </p>
        )}
      </section>
    );
  }

  /* ------------------------------------------------------------- replied ---- */
  return (
    <section className="bs bs-reading m-plate" aria-label="Pragya's answer on the matter">
      <header className="bs-head">
        <div className="bs-drafted-top">
          <span className="t-eyebrow">SHE ANSWERED</span>
          <button className="m-chip" onClick={reset}>
            <Icon name="close" size={12} />
            table something else
          </button>
        </div>
        <p className="bs-matter t-mono">You tabled: {matter.trim()}</p>
      </header>

      <blockquote className="bs-because">
        <p className="t-narrative">{turn.reply}</p>
      </blockquote>

      {/* ------------------------------------------- what the turn actually did */}
      <div className="m-well bs-facts" data-deep>
        <dl>
          <Fact label="STAGE" value={`${turn.stage} · ${turn.stage_name}`} />
          {/* The field names its own unit, so the unit may be printed. Twin and
              turn spend are both tenant-initiated and both owed a number. */}
          <Fact label="THIS TURN COST" value={`USD ${grouped(turn.cost_usd)}`} />
          {turn.command_summary !== null && (
            <Fact label="SHE IS ABOUT TO" value={turn.command_summary} />
          )}
          {turn.advanced_to !== null && (
            <Fact label="ADVANCED TO" value={String(turn.advanced_to)} />
          )}
          {turn.artifacts_written.length > 0 && (
            <Fact label="WROTE" value={turn.artifacts_written.join(", ")} />
          )}
          {turn.reported_delegations.length > 0 && (
            <Fact label="DELEGATED TO" value={turn.reported_delegations.join(", ")} />
          )}
        </dl>
      </div>

      {/* Consequences, each a lamp plus a word — never colour alone. */}
      {(turn.raised_approval || turn.awaiting_confirmation) && (
        <ul className="bs-flags">
          {turn.raised_approval && (
            <li className="bs-flag">
              {/* Sanctioned gold (§2.1): this is literally "this needs you". */}
              <span className="m-lamp" data-lit />
              <span>
                That turn raised a card. It is in your tray, and the estate is
                holding the work until you answer it.
              </span>
            </li>
          )}
          {turn.awaiting_confirmation && (
            <li className="bs-flag">
              <span className="m-lamp" data-lit />
              <span>
                She is waiting on your confirmation before she goes any further.
                That is taken in the Thread, where she asked for it.
              </span>
            </li>
          )}
        </ul>
      )}

      {(turn.needs_step_up || turn.needs_oob) && (
        <p className="bs-gap t-mono">
          {turn.needs_step_up
            ? "That turn asked you to prove it is you"
            : "That turn asked for a second channel"}
          . The ceremony belongs to the act that needs it, and this panel takes
          no certified act — it is taken where the act is, in the Tray or in the
          Thread.
        </p>
      )}

      {/* ------------------------------------------------------------- filing */}
      {filed === null ? (
        <>
          <div className="bs-acts">
            <button className="m-btn" disabled={busy} onClick={() => void fileIt()}>
              <Icon name="record" size={14} />
              File it as a proposition
            </button>
          </div>
          <p className="bs-gh-note t-mono">
            It is filed <strong>untested</strong>: nothing has been simulated, and
            the pipeline refuses any other grade without a run behind it. The
            Boardroom can send it down to the Glasshouse to be graded, and can
            adopt it once it is on the record.
          </p>
        </>
      ) : (
        <p className="bs-filed" role="status">
          {filed.kind === "written" && (
            <>
              <span className="m-lamp" data-positive aria-hidden="true" />
              Filed as a proposition. It is in the list below, tabled, and can be
              adopted from there.
              <span className="bs-filed-id t-mono">{filed.id}</span>
            </>
          )}
          {filed.kind === "proposed" && (
            <>
              <span className="m-lamp" aria-hidden="true" />
              Proposed rather than filed — Planning records are owned elsewhere
              in this estate, so the change went to their owner as a signal
              rather than straight onto the record.
              {filed.signalId !== null && (
                <span className="bs-filed-id t-mono">{filed.signalId}</span>
              )}
            </>
          )}
          {filed.kind === "refused" && (
            <>
              <span className="m-lamp" data-negative aria-hidden="true" />
              It was not filed, and nothing has been changed.
              <span className="bs-filed-id t-mono">{filed.reason}</span>
            </>
          )}
        </p>
      )}

      {broke !== null && (
        <p className="bs-broke" role="status">
          <span className="m-lamp" data-negative aria-hidden="true" />
          That did not go through, and nothing was recorded.
          <span className="bs-broke-reason t-mono">{broke}</span>
        </p>
      )}
    </section>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="bs-fact">
      <dt className="t-eyebrow">{label}</dt>
      <dd className="bs-fact-value t-mono">{value}</dd>
    </div>
  );
}
