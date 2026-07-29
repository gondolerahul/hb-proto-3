/**
 * Pre-session (VP-03's conventional half, D8 §4): login and register,
 * deliberately unthemed beyond the brand — "a login screen that tries to
 * be an estate is a login screen that is slow." Password reset is a named
 * absence: the backend ships no reset endpoint today (only email
 * verification), so the screen says so instead of pretending (recorded as
 * a build delta; the endpoint is DRIVER/Study work).
 */
import { useState, type FormEvent } from "react";

import { login, register } from "../api/client";

export function PreSession({
  onEntered,
}: {
  onEntered: () => void;
}): JSX.Element {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent): Promise<void> {
    event.preventDefault();
    setBusy(true);
    setProblem(null);
    try {
      if (mode === "login") await login({ email, password });
      else await register({ email, password, full_name: fullName });
      onEntered();
    } catch {
      setProblem(
        mode === "login"
          ? "That email and password did not match."
          : "Registration did not go through — check the details and try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="vh-presession" data-part="pre-session">
      <h1 className="vihara-wordmark">Vihara</h1>
      <form onSubmit={(e) => void submit(e)}>
        {mode === "register" && (
          <label>
            Your name
            <input
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              autoComplete="name"
              required
            />
          </label>
        )}
        <label>
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            required
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            required
          />
        </label>
        {problem !== null && (
          <p role="alert" className="vh-problem">
            {problem}
          </p>
        )}
        <button type="submit" disabled={busy}>
          {mode === "login" ? "Enter" : "Create the estate"}
        </button>
      </form>
      <button
        type="button"
        className="vh-quiet-link"
        onClick={() => setMode(mode === "login" ? "register" : "login")}
      >
        {mode === "login" ? "New here? Register" : "Have an estate? Enter"}
      </button>
      <p className="vh-quiet">
        Forgotten password? Resets are not self-service yet — ask your
        administrator.
      </p>
    </main>
  );
}
