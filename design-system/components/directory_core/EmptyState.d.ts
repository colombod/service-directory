import * as React from "react";

/** EmptyState — dashed card shown when the catalogue resolves to zero services. */
export interface EmptyStateProps {
  title: React.ReactNode;
  hint?: React.ReactNode;
  style?: React.CSSProperties;
}

export function EmptyState(props: EmptyStateProps): React.JSX.Element;
