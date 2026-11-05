import * as React from "react";

/**
 * AmpHeader — the fixed 44px header every Amplifier app shares: mark, app
 * name, word chrome, attention summary, agent button.
 *
 * @startingPoint section="Amplifier app" subtitle="44px header, agent button, attention badge" viewport="700x150"
 */
export interface AmpHeaderProps {
  /** Plain type at 13px/600 — an app does not get its own wordmark. */
  appName: string;
  /** Path to assets/amplifier/amplifier-icon-32.png, relative to the page. */
  markSrc?: string;
  /** How many items need a human; 0 hides the summary. */
  attention?: number;
  /** Singular noun for those items — "run", "session", "node". */
  attentionNoun?: string;
  onAgent?(): void;
  agentOpen?: boolean;
  /** Word chrome: AmpTextControl / AmpFilter. */
  children?: React.ReactNode;
  style?: React.CSSProperties;
}
export interface AgentButtonProps {
  onClick?(): void;
  open?: boolean;
  markSrc?: string;
  style?: React.CSSProperties;
}
export interface AttentionBadgeProps {
  count: number;
  /** 15px variant for rails and inline summaries. */
  small?: boolean;
  style?: React.CSSProperties;
}

export function AmpHeader(props: AmpHeaderProps): React.JSX.Element;
export function AgentButton(props: AgentButtonProps): React.JSX.Element;
export function AttentionBadge(props: AttentionBadgeProps): React.JSX.Element;
