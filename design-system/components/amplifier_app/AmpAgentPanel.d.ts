import * as React from "react";

/**
 * AmpAgentPanel — the Amplifier Agent surface: a 380px violet-edged panel
 * over a page that stays live behind it.
 *
 * @startingPoint section="Amplifier app" subtitle="Violet-edged agent panel over a live page" viewport="700x340"
 */
export interface AmpAgentMessage {
  /** "agent" gets the violet label; anything else is dimmed. */
  from: "agent" | "you" | string;
  text: string;
}
export interface AmpAgentPanelProps {
  log?: AmpAgentMessage[];
  draft?: string;
  onDraft?(next: string): void;
  onSend?(): void;
  onClose?(): void;
  markSrc?: string;
  placeholder?: string;
  style?: React.CSSProperties;
}

export function AmpAgentPanel(props: AmpAgentPanelProps): React.JSX.Element;
