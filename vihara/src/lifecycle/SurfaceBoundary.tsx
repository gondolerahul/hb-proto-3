import { Component, type ErrorInfo, type ReactNode } from "react";
import { Failed } from "./Failed";

/**
 * A real React error boundary, one per surface (R-4 part L, L4).
 *
 * Without one, a `TypeError` in any of eighteen rooms unmounts the entire tree:
 * React 18 discards the whole application when a render throws and nothing
 * catches it. The result is a black page with no rail, no depth ladder and no
 * way out — the shell taken down by a room inside it. This is the wall between
 * the two.
 *
 * Four decisions:
 *
 *  1. **It does not swallow the error.** `componentDidCatch` puts it through
 *     `console.error` with the surface's name and React's component stack, the
 *     message is rendered on screen in `t-mono`, and `onError` is offered for a
 *     caller that wants to report it upstream. A boundary that quietly draws a
 *     friendly panel is how a crash reaches production undiagnosed; every one
 *     of those three trails is deliberate.
 *
 *  2. **Retry is a clean second mount, and it needs no key to be one.** React
 *     unmounts the whole failed subtree when a boundary catches, so clearing
 *     `error` re-mounts the child from scratch — none of the state that led to
 *     the throw survives. That is worth writing down because the obvious
 *     defence against it (keying the child on an attempt counter) is dead
 *     weight, and a reader who does not know React unmounts here will add it.
 *
 *  3. **Changing surface clears the error.** A boundary that latched on the
 *     Tray's crash and then rendered the failure panel over the Library — which
 *     is exactly what happens when the app keeps one boundary and swaps its
 *     children — turns one broken room into a broken product. `surface` is the
 *     identity of what is inside; when it changes, this is a different subject
 *     and the old error is not about it.
 *
 *  4. **The failure face is `Failed`, not a bespoke panel.** A crash and a
 *     failed fetch are different causes with the same consequence — you cannot
 *     see this room — so they get one anatomy and different words. `crashed`
 *     switches the copy.
 *
 * A class component because that is the only thing React gives us:
 * `getDerivedStateFromError` and `componentDidCatch` have no hook equivalent,
 * and the alternatives are a dependency or nothing.
 */

interface SurfaceBoundaryProps {
  /** How a person names what is inside, for the copy: "The Tray". */
  surface: string;
  /** Reported alongside `console.error`, for a caller that ships telemetry. */
  onError?: (error: Error, info: ErrorInfo) => void;
  children: ReactNode;
}

interface SurfaceBoundaryState {
  error: Error | null;
}

export class SurfaceBoundary extends Component<SurfaceBoundaryProps, SurfaceBoundaryState> {
  override state: SurfaceBoundaryState = { error: null };

  static getDerivedStateFromError(thrown: unknown): SurfaceBoundaryState {
    /* A throw is not obliged to be an `Error` — `throw "nope"` is legal, and a
       boundary that assumes otherwise crashes inside the crash handler. */
    return { error: thrown instanceof Error ? thrown : new Error(String(thrown)) };
  }

  override componentDidCatch(error: Error, info: ErrorInfo) {
    // Never silent. The one place the original stack survives.
    console.error(`[vihara] ${this.props.surface} threw while rendering`, error, info.componentStack);
    this.props.onError?.(error, info);
  }

  override componentDidUpdate(previous: SurfaceBoundaryProps) {
    if (this.state.error !== null && previous.surface !== this.props.surface) {
      this.setState({ error: null });
    }
  }

  private readonly retry = () => {
    this.setState({ error: null });
  };

  override render() {
    const { error } = this.state;

    if (error !== null) {
      return (
        <Failed
          what={this.props.surface}
          reason={error.message === "" ? null : error.message}
          onRetry={this.retry}
          crashed
        />
      );
    }

    /* The children bare, not inside a wrapper `<div>`: an element here would
       land in every surface's layout that the surface did not ask for, and
       several of them are grid children whose parent would then lay out the
       wrapper instead of the room. */
    return <>{this.props.children}</>;
  }
}
