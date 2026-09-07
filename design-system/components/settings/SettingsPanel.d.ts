import * as React from "react";

/**
 * SettingsPanel — the right-anchored node/fleet management overlay, plus
 * SettingsSection and KeyValueList.
 *
 * @startingPoint section="Settings" subtitle="Node identity, peers and pairing overlay" viewport="700x400"
 */
export interface SettingsPanelProps {
  open?: boolean;
  title?: string;
  onClose?: () => void;
  children?: React.ReactNode;
}
export interface SettingsSectionProps {
  /** Rendered uppercase at 12px/700 with .06em tracking. */
  title: React.ReactNode;
  children?: React.ReactNode;
  style?: React.CSSProperties;
}
export interface KeyValueListProps {
  items?: Array<{ label: string; value: React.ReactNode }>;
}

export function SettingsPanel(props: SettingsPanelProps): React.JSX.Element | null;
export function SettingsSection(props: SettingsSectionProps): React.JSX.Element;
export function KeyValueList(props: KeyValueListProps): React.JSX.Element;
