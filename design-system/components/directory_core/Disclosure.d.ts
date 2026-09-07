import * as React from "react";

/** Disclosure — collapsible panel with the accent +/− marker (the "Register a service" panel). */
export interface DisclosureProps {
  title: React.ReactNode;
  open?: boolean;
  children?: React.ReactNode;
  style?: React.CSSProperties;
}

export function Disclosure(props: DisclosureProps): React.JSX.Element;
