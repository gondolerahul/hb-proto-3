/**
 * The icon set. Inline SVG on a 24-grid, 1.6 stroke, round caps and joins.
 *
 * The brand's no-emoji rule is absolute, and ui-ux-pro-max lists emoji-as-icon
 * as a priority-4 anti-pattern. These are hand-set rather than pulled from a
 * library so the stroke weight matches the hairline grammar in material.css —
 * a 2px-stroke library icon beside a 1px rule looks like two design systems.
 */

const PATHS = {
  // navigation
  up: "M12 19V5M5 12l7-7 7 7",
  down: "M12 5v14M19 12l-7 7-7-7",
  back: "M19 12H5M12 19l-7-7 7-7",
  forward: "M5 12h14M12 5l7 7-7 7",
  close: "M18 6 6 18M6 6l12 12",
  chevron: "M9 18l6-6-6-6",
  // acts
  check: "M20 6 9 17l-5-5",
  hold: "M10 15V9M14 15V9",
  undo: "M9 14 4 9l5-5M4 9h11a5 5 0 0 1 0 10h-4",
  search: "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16ZM21 21l-4.3-4.3",
  filter: "M3 5h18M6 12h12M10 19h4",
  // objects
  record: "M4 4h11l5 5v11H4zM15 4v5h5",
  ledger: "M4 5a2 2 0 0 1 2-2h13v18H6a2 2 0 0 1-2-2zM9 3v18",
  district: "M3 20h18M6 20V9l6-4 6 4v11M10 20v-5h4v5",
  colleague: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM5 21a7 7 0 0 1 14 0",
  key: "M15 3a6 6 0 1 1-4.2 10.3L9 15H7v2H5v2H2v-3l8.8-8.8A6 6 0 0 1 15 3ZM16.5 7.5h.01",
  seal: "M12 2 4 6v6c0 5 3.4 8.7 8 10 4.6-1.3 8-5 8-10V6z",
  // states
  alert: "M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z",
  clock: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM12 7v5l3 2",
  trend: "M22 7l-8.5 8.5-4-4L2 19",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({
  name,
  size = 16,
  className,
}: {
  name: IconName;
  size?: number;
  className?: string;
}) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      style={{ flex: "none" }}
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
