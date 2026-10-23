import { useState } from "react";
import type { RevisionMap, RevisionNotes } from "../types";
import { networkMessage } from "../utils";
import Dialog from "./Dialog";

export default function StudyEditor({kind, data, onSave, onClose}: {
  kind: "map" | "notes"; data: RevisionMap | RevisionNotes; onSave: (data: RevisionMap | RevisionNotes) => Promise<void>; onClose: () => void;
}) {
  const [draft, setDraft] = useState(() => structuredClone(data));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const notes = draft as RevisionNotes;
  async function save() {
    setSaving(true); setError("");
    try { await onSave(kind === "notes" ? {...notes, sections:notes.sections.map(section => ({...section,bullets:section.bullets.map(line => line.trim()).filter(Boolean)})),pitfalls:notes.pitfalls.map(line => line.trim()).filter(Boolean)} : draft); onClose(); }
    catch(error) { setError(networkMessage(error)); }
    finally { setSaving(false); }
  }
  return <Dialog title={kind === "notes" ? "编辑精简提纲" : "编辑导图概述"} onClose={() => { if (!saving) onClose(); }}>
    <form id="study-edit" className="content-form" onSubmit={event => {event.preventDefault();void save();}}>
      <p className="muted text-sm">保存后，预览和 Word 导出都会使用修改后的内容。手动编辑不调用 AI。</p>
      <label>标题<input required maxLength={kind === "notes" ? 200 : 28} value={draft.title} onChange={event => setDraft({...draft,title:event.target.value})}/></label>
      <label>主线概述<textarea required={kind === "map"} maxLength={kind === "notes" ? 8000 : 140} value={draft.overview} onChange={event => setDraft({...draft,overview:event.target.value})}/></label>
      {kind === "notes" && <>
        {notes.sections.map((section,index) => <fieldset key={index} className="notes-edit-section"><legend>主题 {index+1}</legend>
          <label>主题名<input required maxLength={200} value={section.heading} onChange={event => setDraft({...notes,sections:notes.sections.map((item,i) => i === index ? {...item,heading:event.target.value} : item)})}/></label>
          <label>核心结论（每行一条，保留完整公式和条件）<textarea required value={section.bullets.join("\n")} onChange={event => setDraft({...notes,sections:notes.sections.map((item,i) => i === index ? {...item,bullets:event.target.value.split("\n")} : item)})}/></label>
          <button type="button" className="text-link" disabled={notes.sections.length <= 1} onClick={() => setDraft({...notes,sections:notes.sections.filter((_,i) => i !== index)})}>移除这个主题</button>
        </fieldset>)}
        <button type="button" className="button secondary" disabled={notes.sections.length >= 64} onClick={() => setDraft({...notes,sections:[...notes.sections,{heading:"新主题",bullets:["请输入核心结论"],source_refs:[]}]})}>添加主题</button>
        <label>易混与边界（每行一条，没有可以留空）<textarea value={notes.pitfalls.join("\n")} onChange={event => setDraft({...notes,pitfalls:event.target.value ? event.target.value.split("\n") : []})}/></label>
        <p className="muted text-sm">以精简为目标，不再因单条字数或主题数量略多而拒绝保存。</p>
      </>}
    </form>
    {error && <p className="error-message my-4" role="alert">{error}</p>}
    <div className="dialog-actions"><button className="button secondary" disabled={saving} onClick={onClose}>取消</button><button className="button primary" form="study-edit" disabled={saving} type="submit">{saving ? "保存中…" : "保存修改"}</button></div>
  </Dialog>;
}
