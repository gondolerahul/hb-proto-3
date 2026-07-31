import { useState, type FormEvent } from "react";
import { login, register } from "../api/client";
import "./presession.css";

/**
 * Pre-session · login, register, and the absence between them (R-4 §3, A1).
 *
 * **The R2 ruling governs this file: pre-session stays conventional and unthemed
 * beyond the brand.** A login screen that tries to be an estate is a login screen
 * that is slow, so there is no atmosphere here, no world renderer, no depth
 * ladder and no glass — one plate on the ground, the mark, and the fields, in
 * the order every login screen on earth puts them. Restraint *is* the design
 * decision; the estate begins on the other side of the button.
 *
 * Three things a reader would otherwise have to reverse-engineer:
 *
 *  1. **No `<Background>` import, deliberately.** It is not only a look: the
 *     background probes the device tier and may `await import()` three.js. The
 *     first paint a person ever sees of this product must not be waiting on a
 *     3D scene it is about to throw away.
 *
 *  2. **The failure copy is a switch on the status, not one catch-all.** "That
 *     email and password did not match" is a *claim*, and it is false when the
 *     server never answered or the rate limiter refused. A screen that says the
 *     same sentence for six different causes teaches people to distrust it, and
 *     one of those causes (429) is the one they can actually act on.
 *
 *  3. **The forgotten-password block is a rendered gap (DESIGN_CONTRACT §7.4),
 *     not an oversight.** The backend ships email verification and no reset
 *     endpoint. The honest form of that is a sentence saying so with no link
 *     under it — a link that goes nowhere is a worse answer than no link.
 */

type Mode = "login" | "register";

/** Every branch is a different true sentence about what just happened. */
function problemFor(mode: Mode, error: unknown): string {
  const status = (error as { response?: { status?: number } } | null)?.response?.status;

  if (status === undefined) {
    return "The estate did not answer. It may be down, or this browser may be offline.";
  }
  if (status === 429) {
    return "Too many attempts from here. Wait a minute, then try once more.";
  }
  if (status === 409) {
    return "There is already an estate for that email. Enter instead of opening one.";
  }
  if (status === 422 || status === 400) {
    return mode === "login"
      ? "Those details were not accepted — check the email address."
      : "Those details were not accepted — check the email address, and that the password is long enough.";
  }
  if (status === 401 || status === 403) {
    return "That email and password did not match.";
  }
  if (status >= 500) {
    return "Something failed at our end. Nothing was created or changed.";
  }
  return mode === "login"
    ? "That email and password did not match."
    : "Registration did not go through. Check the details and try again.";
}

export function PreSession({
  onEntered,
  returningTo = null,
}: {
  onEntered: () => void;
  /** Where the session ended, if it ended somewhere. The URL is the memory —
   *  nothing is stored, because nothing may be (VP-01). */
  returningTo?: string | null;
}) {
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent): Promise<void> {
    event.preventDefault();
    setBusy(true);
    setProblem(null);
    try {
      if (mode === "login") {
        await login({ email, password });
      } else {
        await register({
          email,
          password,
          full_name: fullName,
          // Omitted rather than sent empty: an estate with a blank name is a
          // rail with a blank name, and "" is a value we would have invented.
          ...(companyName.trim().length > 0 ? { company_name: companyName.trim() } : {}),
        });
      }
      onEntered();
    } catch (error) {
      setProblem(problemFor(mode, error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="ps">
      <div className="ps-col vh-enter">
        <header className="ps-brand">
          <span className="ps-mark" aria-hidden="true">
            <span className="ps-mark-dot" />
          </span>
          <h1 className="ps-word">Vihara</h1>
        </header>

        {/* A plate and nothing else. `m-ticks` was tried here and taken out: the
            instrument register is the estate's voice, and the R2 ruling asks
            this screen not to speak it. */}
        <form className="ps-card m-plate" onSubmit={(e) => void submit(e)}>
          <span className="t-eyebrow">
            {mode === "login" ? "ENTER THE ESTATE" : "OPEN AN ESTATE"}
          </span>

          {mode === "register" && (
            <>
              <label className="ps-field">
                <span className="ps-label">Your name</span>
                <input
                  className="ps-input m-well"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  autoComplete="name"
                  required
                />
              </label>
              <label className="ps-field">
                <span className="ps-label">
                  Company <span className="t-subtle">· optional</span>
                </span>
                <input
                  className="ps-input m-well"
                  value={companyName}
                  onChange={(e) => setCompanyName(e.target.value)}
                  autoComplete="organization"
                />
              </label>
            </>
          )}

          <label className="ps-field">
            <span className="ps-label">Email</span>
            <input
              className="ps-input m-well"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              autoFocus
              required
            />
          </label>

          <label className="ps-field">
            <span className="ps-label">Password</span>
            <input
              className="ps-input m-well"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              required
            />
          </label>

          {/* Never colour alone (§4): the lamp is the fast read, the sentence is
              the correct one. */}
          {problem !== null && (
            <p className="ps-problem" role="alert">
              <span className="m-lamp ps-problem-lamp" data-negative />
              <span>{problem}</span>
            </p>
          )}

          <button className="m-btn ps-submit" type="submit" disabled={busy}>
            {busy
              ? mode === "login"
                ? "Entering…"
                : "Opening…"
              : mode === "login"
                ? "Enter"
                : "Open the estate"}
          </button>

          {returningTo !== null && (
            <p className="ps-return t-mono">You will land back on {returningTo}.</p>
          )}
        </form>

        <p className="ps-swap">
          <button
            type="button"
            className="ps-swap-btn"
            onClick={() => {
              setMode(mode === "login" ? "register" : "login");
              setProblem(null);
            }}
          >
            {mode === "login" ? "New here? Open an estate" : "Have an estate? Enter"}
          </button>
        </p>

        <hr className="m-rule-fade ps-rule" />

        {/* §7.4 — where the platform has a real gap, render the gap. */}
        <section className="ps-gap">
          <span className="t-eyebrow">FORGOTTEN PASSWORD</span>
          <p className="ps-gap-note t-mono">
            There is no link here because there is no reset. This platform ships
            no password-reset endpoint, so nobody can send you one — ask whoever
            administers the estate to set a new password for you.
          </p>
        </section>
      </div>
    </main>
  );
}
