import * as React from "react";

export interface ServiceLink { label: string; host?: string; url: string }

export interface Service {
  name: string;
  description?: string;
  category?: string;
  tags?: string[];
  icon?: string;
  owner?: string;
  docs_url?: string;
  links?: ServiceLink[];
  /** "static" rows are read-only; only "dynamic" rows get a remove control. */
  source?: "static" | "dynamic";
  view_url?: string;
  view_kind?: "auto" | "iframe" | "json";
  view_refresh_seconds?: number;
}

/**
 * ServiceRow — one service in the catalogue table.
 *
 * @startingPoint section="Catalogue" subtitle="Service rows, static and dynamic" viewport="700x150"
 */
export interface ServiceRowProps {
  service: Service;
  status?: "up" | "down" | "unknown";
  selected?: boolean;
  /** Sidebar density: hides description, addresses and meta columns. */
  compact?: boolean;
  onOpen?: (service: Service) => void;
  /** Only rendered when service.source === "dynamic". */
  onRemove?: (service: Service) => void;
}

export function ServiceRow(props: ServiceRowProps): React.JSX.Element;
