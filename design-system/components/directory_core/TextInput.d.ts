import * as React from "react";

/**
 * TextInput — the product's only text field, including the masked-SVG search variant.
 *
 * @startingPoint section="Core" subtitle="Filter field, token field and form inputs" viewport="700x150"
 */
export interface TextInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  /** filter = sunken 13px with icon slot; sm = settings/pairing; md = forms. */
  size?: "filter" | "sm" | "md";
  /** Renders the magnifier mask in the 28px left inset. Pair with size="filter". */
  search?: boolean;
}

export function TextInput(props: TextInputProps): React.JSX.Element;
