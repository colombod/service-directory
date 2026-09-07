import * as React from "react";

/**
 * Toast, Menu, Modal, BottomSheet — everything that overlaps live content,
 * and therefore everything that is allowed a shadow.
 *
 * @startingPoint section="muxplex overlays" subtitle="Toast, menu, modal and bottom sheet" viewport="700x400"
 */
export interface ToastProps { children?: React.ReactNode; style?: React.CSSProperties }
export interface MenuOption { label: string; tone?: "default" | "err" }
export interface MenuProps {
  items?: MenuOption[];
  onSelect?: (item: MenuOption) => void;
  style?: React.CSSProperties;
}
export interface ModalProps {
  open?: boolean;
  title?: React.ReactNode;
  onClose?: () => void;
  children?: React.ReactNode;
  width?: number;
}
export interface SheetOption { name: string; bell?: boolean; time?: string }
export interface BottomSheetProps {
  open?: boolean;
  items?: SheetOption[];
  onSelect?: (item: SheetOption) => void;
  onClose?: () => void;
}

export function Toast(props: ToastProps): React.JSX.Element;
export function Menu(props: MenuProps): React.JSX.Element;
export function Modal(props: ModalProps): React.JSX.Element | null;
export function BottomSheet(props: BottomSheetProps): React.JSX.Element | null;
