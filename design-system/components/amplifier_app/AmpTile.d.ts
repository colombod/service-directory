import * as React from "react";

/**
 * AmpTile / AmpTileGrid / AmpRailRow — the overview→focus shell every
 * Amplifier app is built from: a grid of equal-weight tiles that condenses
 * into a 240px rail when one item is selected.
 *
 * @startingPoint section="Amplifier app" subtitle="Overview tile, tile grid, focused rail row" viewport="700x340"
 */
export type AmpTone = "ok" | "err" | "warn" | "accent" | "attention" | "dim";

export interface AmpTileProps {
  name: string;
  /** Status word, shown verbatim — never claim an unobserved state. */
  status?: string;
  statusTone?: AmpTone;
  summary?: string;
  /** Monospace output of the item itself, bottom-anchored in the well. */
  preview?: string;
  /** Opaque corner chip: owner, host, device. */
  tag?: string;
  /** > 0 draws the violet edge, glow and count badge. */
  attention?: number;
  onOpen?(): void;
  style?: React.CSSProperties;
}
export interface AmpTileGridProps {
  children?: React.ReactNode;
  style?: React.CSSProperties;
}
export interface AmpRailRowProps {
  name: string;
  status?: string;
  statusTone?: AmpTone;
  meta?: string;
  attention?: number;
  selected?: boolean;
  onOpen?(): void;
  style?: React.CSSProperties;
}

export function AmpTile(props: AmpTileProps): React.JSX.Element;
export function AmpTileGrid(props: AmpTileGridProps): React.JSX.Element;
export function AmpRailRow(props: AmpRailRowProps): React.JSX.Element;
export function ampEdge(state: { attention?: number; selected?: boolean; hot?: boolean }): string;
