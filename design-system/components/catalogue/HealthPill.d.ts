import * as React from "react";

/**
 * HealthPill — up / down / unknown status pill for a service row or peer.
 *
 * @startingPoint section="Catalogue" subtitle="Health and reachability pills" viewport="700x150"
 */
export interface HealthPillProps {
  status?: "up" | "down" | "unknown";
  /** Override the visible text; defaults to the status word, capitalized by CSS. */
  label?: string;
  style?: React.CSSProperties;
}

export function HealthPill(props: HealthPillProps): React.JSX.Element;
