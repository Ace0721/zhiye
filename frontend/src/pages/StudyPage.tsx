import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Download, Sparkles } from "lucide-react";
import { api, isDesktop } from "../api";
import MindMap from "../components/MindMap";
import ProgressBar from "../components/ProgressBar";
import type { RevisionMap, RevisionNotes, StudyState } from "../types";
import { networkMessage, safeFilename } from "../utils";

type Kind = "map" | "notes";
type State = StudyState<RevisionMap | RevisionNotes>;

export default function StudyPage() {
  const { deckId } = useParams();
  const [tab, setTab] = useState<Kind>("map");
  const [states, setStates] = useState<Partial<Record<Kind, State>>>({});
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [retry, setRetry] = useState(0);
  const [saving, setSaving] = useState(false);
  const [starting, setStarting] = useState(false);
  const state = states[tab];
  const busy = starting || state?.status === "queued" || state?.status === "generating";
  useEffect(() => { setStates({}); }, [deckId]);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    setError("");
    async function poll() {
      try {
        const result = await api.studyState(Number(deckId), tab, controller.signal);
        if (controller.signal.aborted) return;
        setStates(previous => ({ ...previous, [tab]: result }));
        if (result.status === "queued" || result.status === "generating") timer = setTimeout(poll, 1000);
      } catch (error) { if (!controller.signal.aborted) setError(networkMessage(error)); }
    }
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [deckId, tab, retry]);
  async function generate() {
    if (busy) return;
    setStarting(true); setError(""); setNotice("");
    const kind = tab;
    try {
      const result = await api.generateStudy(Number(deckId), kind);
      setStates(previous => ({ ...previous, [kind]: result }));
      setRetry(value => value + 1);
    } catch (error) { setError(networkMessage(error)); }
    finally { setStarting(false); }
  }
  async function download() {
    const notes = states.notes?.data as RevisionNotes | null;
    if (!notes || saving) return;
    setSaving(true); setError("");
    try {
      const blob = await api.studyWord(Number(deckId));
      const filename = safeFilename(notes.title).replace(/\.md$/, "-精简复习资料.docx");
      if (isDesktop()) {
        const { invoke } = await import("@tauri-apps/api/core");
        const path = await invoke<string | null>("save_study_docx", { filename, content: Array.from(new Uint8Array(await blob.arrayBuffer())) });
        if (path) setNotice("Word 已保存");
      } else {
        const url = URL.createObjectURL(blob), anchor = document.createElement("a");
        anchor.href = url; anchor.download = filename; document.body.append(anchor); anchor.click(); anchor.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000); setNotice("Word 下载已开始");
      }
    } catch (error) { setError(networkMessage(error)); }
    finally { setSaving(false); }
  }
  const notes = tab === "notes" ? state?.data as RevisionNotes | null : null;
  const map = tab === "map" ? state?.data as RevisionMap | null : null;
  const noteLength = notes ? Array.from(notes.title + notes.overview + notes.sections.map(section => section.heading + section.bullets.join("")).join("") + notes.pitfalls.join("")).length : 0;
  return <div className="study-page">
    <Link className="back-link" to="/"><ArrowLeft size={16} />我的课件</Link>
    <span className="eyebrow block mt-8">CONNECT IDEAS. KEEP THE ESSENTIALS.</span>
    <h1 className="page-title">把知识，串起来<span className="accent">。</span></h1>
    <p className="page-subtitle">让 AI 梳理概念关系，压缩复习主线。每种内容独立生成，保存在本机，随时回看。</p>
    <div className="study-tabs mt-8" role="tablist" aria-label="复习方式">
      <button role="tab" aria-selected={tab === "map"} aria-controls="study-result" onClick={() => setTab("map")}>逻辑思维导图</button>
      <button role="tab" aria-selected={tab === "notes"} aria-controls="study-result" onClick={() => setTab("notes")}>AI 精简提纲</button>
      <Link className="text-link" to={`/decks/${deckId}`}>刷卡自测 →</Link>
    </div>
    <div className="study-heading"><div><h2>{tab === "map" ? "先看结构，再理解细节" : "只留最该掌握的内容"}</h2>
      <p className="muted text-sm">{tab === "map" ? "按主题分组 · 标明概念关系 · 点击逐层展开" : "合并重复概念 · 保留公式与条件 · 正文最多1600字"}</p></div>
      <div className="flex gap-2 flex-wrap">
        {tab === "notes" && state?.status === "completed" && <button className="button secondary" disabled={saving} onClick={() => void download()}><Download size={17} />{saving ? "保存中…" : "下载 Word"}</button>}
        <button className="button primary" disabled={busy} onClick={() => void generate()}><Sparkles size={17} />{busy ? "AI 正在整理…" : state?.data ? "重新生成" : "开始 AI 生成"}</button>
      </div>
    </div>
    <p className="study-api-note">点击生成会调用你设置的云端 API，可能产生厂商费用；查看缓存和下载 Word 不再次调用。</p>
    {state?.source_type === "knowledge_cards" && <p className="study-source-note">这份旧课件未保留解析正文，本次以已有知识点为资料。重新上传后可使用完整解析正文。</p>}
    {error && <div className="error-message my-4" role="alert">{error}<button className="text-link ml-3" onClick={() => setRetry(value => value + 1)}>重新连接</button></div>}
    {state?.status === "failed" && <div className="error-message my-4" role="alert">{state.error}。可点击上方按钮重试。</div>}
    {notice && <p className="success-message my-4" role="status">{notice}</p>}
    {busy && <div className="study-generating" role="status"><h3>{(state?.progress ?? 0) < 75 ? "正在提炼资料与知识主线" : "正在组织主题与检查输出"}</h3><ProgressBar value={state?.progress ?? 0} label="AI 整理进度" /><p>进度按实际处理阶段更新，等待模型响应时会暂时停留。</p></div>}
    {!state && !error && <p className="muted my-6">正在读取本地记录…</p>}
    {state?.status === "idle" && <div className="study-empty"><span>从零散的知识，到清晰的主线</span><p>{tab === "map" ? "AI 将归纳主题、核心概念及其关系，不再平铺知识卡标题。" : "AI 将筛选和合并内容，生成短提纲，不再把每张卡的解释抄进 Word。"}</p></div>}
    <div id="study-result" role="tabpanel" aria-label={tab === "map" ? "逻辑思维导图" : "AI 精简提纲"}>
      {state?.status === "completed" && map && <><div className="study-overview"><h2>{map.title}</h2><p>{map.overview}</p></div><MindMap key={`${deckId}-${JSON.stringify(map)}`} map={map} /></>}
      {state?.status === "completed" && notes && <section className="study-notes ai-notes"><div className="notes-meta">AI 归纳 · {notes.sections.length} 个主题 · {noteLength} 字符</div><h2>{notes.title}</h2><p className="notes-overview">{notes.overview}</p>{notes.sections.map((section, index) => <article key={index}><h3><span>{String(index + 1).padStart(2, "0")}</span>{section.heading}</h3><ul>{section.bullets.map((bullet, i) => <li key={i}>{bullet}</li>)}</ul></article>)}{notes.pitfalls.length > 0 && <article><h3>易混与边界</h3><ul>{notes.pitfalls.map((item, i) => <li key={i}>{item}</li>)}</ul></article>}</section>}
    </div>
    <p className="muted text-xs my-5">AI 归纳可能遗漏或误解内容，请对照原课件核对公式、前提和结论。</p>
  </div>;
}
