import * as React from "react";

/**
 * FilterInput — the session filter field, with its overlaid clear button.
 * Field — a labelled settings row.
 *
 * @startingPoint section="muxplex core" subtitle="Filter field and settings field rows" viewport="700x150"
 */
export interface FilterInputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "value" | "onChange"> {
  value?: string;
  onValueChange?: (value: string) => void;
  onClear?: () => void;
  /** Uppercase caption before the field (sidebar instance grows to fill). */
  caption?: string;
}
export interface FieldProps {
  label: React.ReactNode;
  helper?: React.ReactNode;
  children?: React.ReactNode;
}

export function FilterInput(props: FilterInputProps): React.JSX.Element;
export function Field(props: FieldProps): React.JSX.Element;
