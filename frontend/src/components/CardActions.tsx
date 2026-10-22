import { useState } from "react";
import { Pencil, RefreshCw, Trash2 } from "lucide-react";
import { api } from "../api";
import type { KnowledgeCard } from "../types";
import { networkMessage } from "../utils";
import Dialog from "./Dialog";

export default function CardActions({card, disabled, onChanged, onDeleted, onBusy}: {
  card: KnowledgeCard; disabled: boolean; onChanged: (card: KnowledgeCard) => void; onDeleted: () => void; onBusy: (value: boolean) => void;
}) {
  const [mode, setMode] = useState<"edit" | "delete" | "regenerate">();
  const [draft, setDraft] = useState(card);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  function open(next: typeof mode) { setDraft(structuredClone(card)); setError(""); setMode(next); }
  async function perform() {
    if (busy) return;
    setBusy(true); onBusy(true); setError("");
    try {
      if (mode === "delete") { await api.deleteCard(card.id); onDeleted(); }
      else onChanged(mode === "edit" ? await api.saveCard(draft) : await api.regenerateCard(card));
      setMode(undefined);
    } catch (error) { setError(networkMessage(error)); }
    finally { setBusy(false); onBusy(false); }
  }
  return <>
    <div className="card-actions"><button disabled={disabled} onClick={() => open("edit")}><Pencil size={14}/>编辑</button><button disabled={disabled} onClick={() => open("regenerate")}><RefreshCw size={14}/>重新生成这一张</button><button disabled={disabled} onClick={() => open("delete")}><Trash2 size={14}/>删除</button></div>
    {mode && <Dialog title={mode === "edit" ? "编辑知识卡" : mode === "delete" ? "删除这张卡" : "重新生成这一张"} onClose={() => { if (!busy) setMode(undefined); }}>
      {mode === "edit" ? <form id="card-edit" className="content-form" onSubmit={event => { event.preventDefault(); void perform(); }}>
        <p className="muted text-sm">修改题目、选项或正确答案会重置这张卡的答题记录；只改解释和重点则保留记录。</p>
        <label>标题<input required maxLength={16} value={draft.title} onChange={e => setDraft({...draft,title:e.target.value})}/></label>
        <label>人话解释<textarea required value={draft.plain_explanation} onChange={e => setDraft({...draft,plain_explanation:e.target.value})}/></label>
        <label>关键点<input required maxLength={40} value={draft.key_point} onChange={e => setDraft({...draft,key_point:e.target.value})}/></label>
        <label>题目<textarea required maxLength={60} value={draft.question} onChange={e => setDraft({...draft,question:e.target.value})}/></label>
        {draft.options.map((option,index) => <label key={index}>选项 {"ABCD"[index]}<input required value={option} onChange={e => setDraft({...draft,options:draft.options.map((value,i) => i === index ? e.target.value : value)})}/></label>)}
        <label>正确答案<select value={draft.correct_index} onChange={e => setDraft({...draft,correct_index:Number(e.target.value)})}>{draft.options.map((_,index) => <option key={index} value={index}>{"ABCD"[index]}</option>)}</select></label>
        <label>再讲一遍<textarea required value={draft.reexplain} onChange={e => setDraft({...draft,reexplain:e.target.value})}/></label>
      </form> : <p className="leading-7 my-5">{mode === "delete" ? "将删除这张卡及其答题记录，回炉队列中的同一张卡也会移除。" : "只调用 AI 重写当前知识点，不影响其他卡片；会使用你的 API 额度。题目改变时会重置这张卡的答题记录。"}</p>}
      {error && <p className="error-message my-4" role="alert">{error}</p>}
      <div className="dialog-actions"><button className="button secondary" disabled={busy} onClick={() => setMode(undefined)}>取消</button><button className="button primary" disabled={busy} form={mode === "edit" ? "card-edit" : undefined} type={mode === "edit" ? "submit" : "button"} onClick={mode === "edit" ? undefined : () => void perform()}>{busy ? "处理中…" : mode === "edit" ? "保存修改" : mode === "delete" ? "确认删除" : "开始重新生成"}</button></div>
    </Dialog>}
  </>;
}
