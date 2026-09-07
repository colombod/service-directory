import * as React from "react";
import { Service } from "../catalogue/ServiceRow";

/**
 * ServiceDetail — the metadata + actions view opened by clicking a catalogue row.
 *
 * @startingPoint section="Viewer" subtitle="Service detail pane with Open here" viewport="700x400"
 */
export interface ServiceDetailProps {
  service: Service;
  status?: "up" | "down" | "unknown";
  /** Dispatches on service.view_kind: auto probes, iframe embeds, json renders a tree. */
  onOpenHere?: (service: Service) => void;
}

export function ServiceDetail(props: ServiceDetailProps): React.JSX.Element;
