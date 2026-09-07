import * as React from "react";

/** JsonTree — collapsible monospace JSON renderer for json-kind services. */
export interface JsonTreeProps {
  data: unknown;
  style?: React.CSSProperties;
}

export function JsonTree(props: JsonTreeProps): React.JSX.Element;
