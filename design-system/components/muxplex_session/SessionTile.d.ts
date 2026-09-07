import * as React from "react";

/**
 * SessionTile — one live tmux session in the grid.
 *
 * @startingPoint section="muxplex sessions" subtitle="Session tiles: rest, hover, bell and loading" viewport="760x340"
 */
export interface SessionTileProps {
  name: string;
  /** Dense right-aligned metadata (window count, last activity). Fades on hover. */
  meta?: React.ReactNode;
  /** Live terminal output, bottom-anchored monospace. */
  preview?: string;
  /** > 0 renders the pulsing amber count badge, amber border and inner glow. */
  bellCount?: number;
  /** Dot mode: amber left edge bar only, no glow. */
  edgeBell?: boolean;
  /** Opaque chip drawn inside the preview. Never translucent — see the
   *  legibility invariant in style.css. */
  deviceTag?: string;
  loading?: boolean;
  onClick?: () => void;
  style?: React.CSSProperties;
}

export function SessionTile(props: SessionTileProps): React.JSX.Element;
