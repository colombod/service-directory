import * as React from "react";
import { Service } from "./ServiceRow";

/** NodeGroup — one section per origin node in the catalogue. */
export interface NodeGroupProps {
  /** The origin node name, rendered uppercase. */
  origin: string;
  description?: string;
  children?: React.ReactNode;
  style?: React.CSSProperties;
}

/** ServiceTable — the uniform, borderless-header table of service rows. */
export interface ServiceTableProps {
  services?: Service[];
  /** name -> status map, as returned by /api/health. */
  health?: Record<string, "up" | "down" | "unknown">;
  compact?: boolean;
  selected?: string;
  onOpen?: (service: Service) => void;
  onRemove?: (service: Service) => void;
}

export function NodeGroup(props: NodeGroupProps): React.JSX.Element;
export function ServiceTable(props: ServiceTableProps): React.JSX.Element;
