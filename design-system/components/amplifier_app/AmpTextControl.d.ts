import * as React from "react";

/**
 * AmpTextControl — word chrome (view, sort, "← All items").
 * AmpFilter — the single filter field, header or rail width.
 *
 * @startingPoint section="Amplifier app" subtitle="Word chrome and the filter field" viewport="700x150"
 */
export interface AmpTextControlProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  /** Renders in the hover colour and sets aria-expanded — for menu triggers. */
  expanded?: boolean;
}
export interface AmpFilterProps {
  value: string;
  onChange(next: string): void;
  placeholder?: string;
  /** Fill the container (focused rail) instead of the 150px header width. */
  wide?: boolean;
  style?: React.CSSProperties;
}

export function AmpTextControl(props: AmpTextControlProps): React.JSX.Element;
export function AmpFilter(props: AmpFilterProps): React.JSX.Element;
