import { useMemo, useState } from "react";
import { ArrowRight, BookOpen, Check, FileText, FolderOpen, Layers3, Network, Plus, Search, Tag, Target, TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../api";
import type { LibraryData, LibraryDeck } from "../types";
import { deckPath, localDate, sessionPath, visibleDecks } from "../library";
import type { LibraryFilter, LibrarySort } from "../library";
import { networkMessage } from "../utils";
import Dialog from "./Dialog";

export function LearningOverview({data}: {data: LibraryData}) {
  const {stats, resume} = data;
  const max = Math.max(1, ...data.activity.map(day => day.count));
  const remaining = resume ? resume.total-resume.answered : 0;
  return <section className="learning-overview">
    <div className="dashboard-heading"><div><span className="eyebrow">A LITTLE EVERY DAY</span><h1>今天，也弄懂一点</h1><p className="muted">你的课件与学习现场，都在这里</p></div>
      <a className="button primary" href="#upload" onClick={event => {event.preventDefault(); document.getElementById("upload")?.scrollIntoView({behavior:"smooth"});}}><Plus size={17}/><span className="desktop-upload-label">上传新课件</span><span className="mobile-upload-label">上传</span></a></div>
    <div className="learning-stats">{[
      [BookOpen,stats.deck_count,"我的课件","份"], [Check,stats.learned_count,"已学知识点","个"],
      [Target,stats.wrong_count,"历史错题","张"], [TrendingUp,stats.today_count,"今日已学","个"],
    ].map(([Icon,value,label,unit]) => { const Glyph = Icon as typeof BookOpen; return <div className="stat-card" key={String(label)}><span className="stat-icon"><Glyph size={19}/></span><div><span className="stat-label">{String(label)}</span><p><strong>{String(value)}</strong><small>{String(unit)}</small></p></div></div>; })}</div>
    <div className="dashboard-focus-grid">
      <div className="resume-panel"><span className="eyebrow">{resume ? "PICK UP WHERE YOU LEFT OFF" : "YOUR NEXT SMALL STEP"}</span>
        <div className="resume-art" aria-hidden="true"><Layers3 size={74} strokeWidth={1}/></div>
        <h2>{resume ? "接着上次，继续学" : stats.card_count ? "选一份课件，开始学习" : "把课件，变成理解"}</h2>
        <p className="resume-title">{resume ? resume.title : stats.card_count ? "每次弄懂一个点，慢慢建立知识框架" : "知识卡、精简提纲、互动导图，按需选择"}</p>
        {resume && <><div className="resume-track"><span style={{width:`${100*resume.answered/resume.total}%`}}/></div>
          <p className="resume-detail">{resume.mode === "wrong" ? "错题复习" : "刷卡学习"} · 第 {resume.index+1} / {resume.total} 张 · {remaining ? `还有 ${remaining} 张未答` : "本轮题目已答完，待确认完成"}</p></>}
        {resume ? <Link className="button light-button" to={sessionPath(resume)}>继续学习<ArrowRight size={17}/></Link> : <a className="button light-button" href="#library" onClick={event => {event.preventDefault(); document.getElementById("library")?.scrollIntoView({behavior:"smooth"});}}>打开我的课件<ArrowRight size={17}/></a>}
      </div>
      <div className="weekly-panel"><div className="flex justify-between items-start"><div><span className="eyebrow">LAST 7 DAYS</span><h2>这一周的积累</h2></div><span className="week-total">{data.activity.reduce((sum,day) => sum+day.count,0)}<small> 日累计知识点</small></span></div>
        <div className="week-bars" role="img" aria-label={data.activity.map(day => `${day.date} 学习${day.count}个知识点`).join("；")}>
          {data.activity.map((day,index) => <div className={`week-day ${index === 6 ? "today" : ""}`} key={day.date}><span className="week-count">{day.count}</span><div className="week-bar-track"><span style={{height:day.count ? `${Math.max(8,100*day.count/max)}%` : "3px"}}/></div><small>{index === 6 ? "今天" : `${Number(day.date.slice(5,7))}/${Number(day.date.slice(8))}`}</small></div>)}
        </div><p className="muted text-xs">按每天答过的知识点去重，同一知识点跨天会分别计数</p>
      </div>
    </div>
  </section>;
}

export default function CourseLibrary({data, onTags}: {data: LibraryData; onTags: (id: number, tags: string[]) => void}) {
  const [query,setQuery] = useState("");
  const [filter,setFilter] = useState<LibraryFilter>("all");
  const [sort,setSort] = useState<LibrarySort>("recent");
  const [editing,setEditing] = useState<LibraryDeck>();
  const [tags,setTags] = useState("");
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState("");
  const decks = useMemo(() => visibleDecks(data.decks,query,filter,sort),[data.decks,query,filter,sort]);
  async function save() {
    if (!editing || busy) return;
    const values = [...new Set(tags.split(/[,，\n]/).map(tag => tag.trim()).filter(Boolean))];
    if (values.length > 6 || values.some(tag => tag.length > 16)) { setError("最多6个标签，每个标签不超过16字"); return; }
    setBusy(true); setError("");
    try { const result = await api.saveTags(editing.id,values); onTags(editing.id,result.tags); setEditing(undefined); }
    catch(error) { setError(networkMessage(error)); } finally { setBusy(false); }
  }
  return <section className="library-section" id="library">
    <div className="section-heading"><div><span className="eyebrow">YOUR STUDY SHELF</span><h2>我的课件<span className="muted ml-2 text-sm font-normal">{data.decks.length} 份</span></h2></div><FolderOpen size={23} className="muted"/></div>
    <div className="library-toolbar"><label className="library-search"><Search size={18}/><input aria-label="搜索课件" placeholder="搜索课件名称、文件名或标签" value={query} onChange={event => setQuery(event.target.value)}/>{query && <button onClick={() => setQuery("")} aria-label="清空搜索">×</button>}</label>
      <select aria-label="课件排序" value={sort} onChange={event => setSort(event.target.value as LibrarySort)}><option value="recent">最近学习</option><option value="newest">最新上传</option><option value="title">名称排序</option><option value="progress">学习进度</option></select></div>
    <div className="library-filters" aria-label="筛选课件">{([['all','全部课件'],['active','学习中'],['wrong','有错题'],['notes','有 Word'],['map','有导图']] as const).map(([value,label]) => <button key={value} aria-pressed={filter === value} className={filter === value ? "selected" : ""} onClick={() => setFilter(value)}>{label}</button>)}<span>{decks.length} 份结果</span></div>
    {decks.length ? <div className="course-grid">{decks.map((deck,index) => {
      const active = deck.sessions.filter(session => !session.completed).sort((a,b) => localDate(b.updated_at).getTime()-localDate(a.updated_at).getTime())[0];
      const completed = deck.sessions.find(session => session.mode === "all" && session.completed);
      return <article className={`course-card cover-${deck.id%4}`} key={deck.id}>
        <div className="course-cover"><span className="course-format">{deck.source_filename.toLowerCase().endsWith('.pptx') ? 'PPTX' : 'PDF'}</span><span className="course-number">{String(index+1).padStart(2,'0')}</span><BookOpen size={42} strokeWidth={1.2}/><div className="cover-lines"/><span className="cover-state">{active ? "学习中" : completed ? "本轮已完成" : deck.learned_count ? "已开始学习" : "等待探索"}</span></div>
        <div className="course-content"><Link to={active ? sessionPath(active) : deckPath(deck)}><h3 title={deck.title}>{deck.title}</h3></Link><p className="course-file" title={deck.source_filename}>{deck.source_filename}</p>
          <div className="course-tags">{deck.tags.map(tag => <button key={tag} onClick={() => {setQuery(tag);setFilter('all');}}>{tag}</button>)}<button className="tag-edit" aria-label={`编辑${deck.title}的标签`} onClick={() => {setEditing(deck);setTags(deck.tags.join('，'));setError('');}}><Tag size={12}/>{deck.tags.length ? "编辑" : "添加标签"}</button></div>
          <div className="course-output-list">{deck.available_outputs.includes('cards') && <span><Layers3 size={13}/>{deck.card_count} 张卡片</span>}{deck.available_outputs.includes('notes') && <span><FileText size={13}/>Word</span>}{deck.available_outputs.includes('map') && <span><Network size={13}/>导图</span>}{!deck.available_outputs.length && <span>内容尚未生成</span>}</div>
          {deck.card_count > 0 && <div className="course-progress"><div><span>已学 {deck.learned_count} / {deck.card_count} 个知识点</span><strong>{Math.round(100*deck.learned_count/deck.card_count)}%</strong></div><div className="course-track"><span style={{width:`${100*deck.learned_count/deck.card_count}%`}}/></div></div>}
          <div className="course-meta"><span>{deck.last_studied_at ? `${localDate(deck.last_studied_at).toLocaleDateString('zh-CN')} 学习` : `${localDate(deck.created_at).toLocaleDateString('zh-CN')} 上传`}</span>{deck.wrong_count > 0 && <Link to={`/decks/${deck.id}?mode=wrong`}>{deck.wrong_count} 张历史错题 ↗</Link>}</div>
          <div className="course-actions"><Link className="course-primary" to={active ? sessionPath(active) : deckPath(deck)}>{active ? "继续学习" : completed ? "查看学习成果" : deck.card_count ? "开始学习" : "打开复习资料"}<ArrowRight size={15}/></Link><Link className="course-materials" to={`/decks/${deck.id}/study?tab=${deck.available_outputs.includes('notes') ? 'notes' : 'map'}`} aria-label={`${deck.title}的资料与导图`}><Network size={17}/></Link></div>
        </div>
      </article>;
    })}</div> : <div className="library-empty"><Search size={28}/><h3>{data.decks.length ? "没有找到匹配的课件" : "从第一份课件开始积累"}</h3><p className="muted">{data.decks.length ? "换个关键词，或清除筛选再试试" : "上传 PDF 或 PPTX，让知识在这里慢慢成形"}</p>{data.decks.length > 0 && <button className="text-link" onClick={() => {setQuery('');setFilter('all');}}>清除搜索与筛选</button>}</div>}
    {editing && <Dialog title="整理课件标签" onClose={() => {if (!busy) setEditing(undefined);}}><p className="muted mb-4">{editing.title} · 最多6个标签，用逗号分隔</p><label className="block">标签<input className="tag-input" value={tags} onChange={event => setTags(event.target.value)} placeholder="例如：大一上，期末，高数" maxLength={120}/></label>{error && <p className="error-message mt-3" role="alert">{error}</p>}<button className="button primary mt-5" disabled={busy} onClick={() => void save()}>{busy ? "正在保存…" : "保存标签"}</button></Dialog>}
  </section>;
}
