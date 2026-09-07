import * as React from "react";

/**
 * SessionPill — floating "back to session" control. FilterPill — a filter toggle.
 *
 * @startingPoint section="muxplex sessions" subtitle="Floating session pill and filter pills" viewport="700x150"
 */
export interface SessionPillProps {
  label: string;
  bell?: boolean;
  onClick?: () => void;
}
export interface FilterPillProps {
  active?: boolean;
  children?: React.ReactNode;
  onClick?: () => void;
}

export function SessionPill(props: SessionPillProps): React.JSX.Element;
export function FilterPill(props: FilterPillProps): React.JSX.Element;
