import * as React from "react";

/**
 * ViewerWelcome — the viewer pane's default/empty state, plus its two siblings
 * ViewerHeader (embed toolbar) and ViewerFallback (can't-embed card).
 *
 * @startingPoint section="Viewer" subtitle="Welcome, embed toolbar and fallback card" viewport="700x400"
 */
export interface ViewerWelcomeProps {
  title?: string;
  hint?: string;
}
export interface ViewerHeaderProps {
  name: string;
  /** External URL for the "open in new tab" affordance. */
  url?: string;
  /** Extra toolbar controls (Reload, Refresh, Auto-refresh, updated-ago). */
  actions?: React.ReactNode;
  onClose?: () => void;
}
export interface ViewerFallbackProps {
  name: string;
  url: string;
  /** The literal reason, e.g. "This service cannot be embedded (X-Frame-Options or CSP frame-ancestors)." */
  reason: string;
}

export function ViewerWelcome(props: ViewerWelcomeProps): React.JSX.Element;
export function ViewerHeader(props: ViewerHeaderProps): React.JSX.Element;
export function ViewerFallback(props: ViewerFallbackProps): React.JSX.Element;
