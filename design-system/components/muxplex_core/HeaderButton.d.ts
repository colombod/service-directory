import * as React from "react";

/**
 * HeaderButton — bordered button for header actions and commit actions.
 *
 * @startingPoint section="muxplex core" subtitle="Header actions, the Agent button and Send" viewport="700x150"
 */
export interface HeaderButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  /** agent = carries the 16px Amplifier mark; commit = accent-dim fill (Send). */
  variant?: "default" | "agent" | "commit";
  icon?: React.ReactNode;
  children?: React.ReactNode;
}

export function HeaderButton(props: HeaderButtonProps): React.JSX.Element;
