import * as React from "react";

/**
 * CategoryChip — accent-weak chip for a service's category, plus its two siblings
 * TagList and ReachableBadge.
 *
 * @startingPoint section="Catalogue" subtitle="Category chip, #tags and the reachable dot" viewport="700x150"
 */
export interface CategoryChipProps {
  children?: React.ReactNode;
  style?: React.CSSProperties;
}
export interface TagListProps {
  tags?: string[];
  style?: React.CSSProperties;
}
export interface ReachableBadgeProps {
  label?: string;
  style?: React.CSSProperties;
}

export function CategoryChip(props: CategoryChipProps): React.JSX.Element;
export function TagList(props: TagListProps): React.JSX.Element;
export function ReachableBadge(props: ReachableBadgeProps): React.JSX.Element;
