import * as React from "react";

/**
 * Surface — the flat content rectangle. Badge — a small status marker.
 *
 * @startingPoint section="muxplex core" subtitle="Flat surface and the badge tones" viewport="700x150"
 */
export interface SurfaceProps extends React.HTMLAttributes<HTMLElement> {
  as?: keyof React.JSX.IntrinsicElements;
  padded?: boolean;
}
export interface BadgeProps {
  /** Fill only when the badge carries a state. accent = device tag, bell = attention. */
  tone?: "neutral" | "accent" | "bell" | "ok" | "warn" | "err";
  pill?: boolean;
  children?: React.ReactNode;
  style?: React.CSSProperties;
}

export function Surface(props: SurfaceProps): React.JSX.Element;
export function Badge(props: BadgeProps): React.JSX.Element;
