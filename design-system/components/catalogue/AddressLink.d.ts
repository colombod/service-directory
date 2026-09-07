import * as React from "react";

/** AddressLink — monospace new-tab link for one resolved host address (Tailnet / LAN). */
export interface AddressLinkProps extends React.AnchorHTMLAttributes<HTMLAnchorElement> {
  /** The host address label from config, e.g. "Tailnet" or "LAN". */
  label: string;
  href: string;
  /** primary for the first (tailnet-preferred) address; secondary for the rest. */
  variant?: "primary" | "secondary";
}

export function AddressLink(props: AddressLinkProps): React.JSX.Element;
