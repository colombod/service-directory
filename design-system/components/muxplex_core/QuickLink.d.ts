import * as React from "react";

/**
 * QuickLink — the app's shared link-button. Read the long comment above
 * .quick-link in style.css before changing anything in this family.
 *
 * @startingPoint section="muxplex core" subtitle="The reference link-control, with and without caption" viewport="700x150"
 */
export interface QuickLinkProps extends React.HTMLAttributes<HTMLElement> {
  as?: "button" | "a";
  /** Drives aria-expanded and the persistent accent-hover colour. */
  expanded?: boolean;
  /** Small uppercase caption placed before the control (sidebar instances). */
  caption?: string;
  children?: React.ReactNode;
}

export function QuickLink(props: QuickLinkProps): React.JSX.Element;
