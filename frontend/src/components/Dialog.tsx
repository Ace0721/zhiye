import { useEffect, useRef, type ReactNode } from "react";
import { X } from "lucide-react";

export default function Dialog({title, children, onClose}: {title: string; children: ReactNode; onClose: () => void}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { const element = dialog.current; element?.showModal(); return () => element?.close(); }, []);
  return <dialog className="content-dialog" ref={dialog} onCancel={event => {event.preventDefault();onClose();}} aria-label={title}>
    <header><h2>{title}</h2><button type="button" aria-label="关闭对话框" onClick={onClose}><X size={20}/></button></header>
    {children}
  </dialog>;
}
