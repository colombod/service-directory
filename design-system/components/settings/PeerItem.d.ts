import * as React from "react";

/** PeerItem — one row in Trusted Peers. PairingCode — the issued one-time code card. */
export interface PeerItemProps {
  name: string;
  baseUrl: string;
  /** "unknown" whenever the peer was not observed this pass — never "down". */
  reachable?: "up" | "unknown";
  onRemove?: () => void;
  last?: boolean;
}
export interface PairingCodeProps {
  code: string;
  ttlSeconds?: number;
}

export function PeerItem(props: PeerItemProps): React.JSX.Element;
export function PairingCode(props: PairingCodeProps): React.JSX.Element;
