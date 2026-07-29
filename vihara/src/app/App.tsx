/**
 * The shell is app-owned, not manifest-composed (D6 §1) — a hostile
 * manifest cannot remove the user's way out of a surface. T7 grows this
 * into the real shell (pre-session → still surface); T1 only proves the
 * toolchain stands.
 */
export function App(): JSX.Element {
  return (
    <main className="vihara-shell">
      <h1 className="vihara-wordmark">Vihara</h1>
      <p className="vihara-quiet">The estate is still.</p>
    </main>
  );
}
