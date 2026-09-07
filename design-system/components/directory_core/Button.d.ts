import * as React from "react";

/**
 * Button — the single button primitive of the Service Directory dashboard.
 *
 * @startingPoint section="Core" subtitle="Primary, secondary and ghost buttons at every size" viewport="700x150"
 */
export interface ButtonProps extends React.HTMLAttributes<HTMLElement> {
  /** primary = accent fill (one per view, max); secondary = bordered; ghost = bare × control. */
  variant?: "primary" | "secondary" | "ghost";
  /** sm 4x10/12px, md 6x12/13px, lg 8x16/13px, xl 9x22/14px. */
  size?: "sm" | "md" | "lg" | "xl";
  /** Render as another tag (e.g. "a" for the fallback "open in a new tab" action). */
  as?: "button" | "a";
  fullWidth?: boolean;
  disabled?: boolean;
  children?: React.ReactNode;
}

export function Button(props: ButtonProps): React.JSX.Element;
