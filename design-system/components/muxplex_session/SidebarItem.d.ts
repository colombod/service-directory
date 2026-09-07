import * as React from "react";

/**
 * SidebarItem — the 120px session card in the rail. DeviceHeader — its grouping heading.
 *
 * @startingPoint section="muxplex sessions" subtitle="Sidebar session rail" viewport="700x400"
 */
export interface SidebarItemProps {
  name: string;
  active?: boolean;
  bell?: boolean;
  preview?: string;
  /** Usually a device Badge or the options button. */
  badge?: React.ReactNode;
  onClick?: () => void;
}
export interface DeviceHeaderProps {
  children?: React.ReactNode;
  version?: string;
}

export function SidebarItem(props: SidebarItemProps): React.JSX.Element;
export function DeviceHeader(props: DeviceHeaderProps): React.JSX.Element;
