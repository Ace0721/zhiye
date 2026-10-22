import { useEffect, useMemo, useRef, useState } from "react";
import type { MapNode, RevisionMap } from "../types";
import Dialog from "./Dialog";
import SourceRefs from "./SourceRefs";
import { networkMessage } from "../utils";

const colors = ["#547c67", "#a77348", "#617ea4", "#9b688a", "#75834c", "#aa685b"];
type Item = { id: string; node: MapNode; depth: number; branch: number; x: number; y: number; parent?: string; path: string[] };

function wrap(text: string): string[] {
  const chars = Array.from(text);
  return [chars.slice(0, 14).join(""), chars.slice(14, 28).join("")].filter(Boolean);
}

export default function MindMap({ map, deckId, onChange }: { map: RevisionMap; deckId: number; onChange: (map: RevisionMap) => Promise<void> }) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<string>("0");
  const [query, setQuery] = useState("");
  const [zoom, setZoom] = useState(1);
  const [width, setWidth] = useState(850);
  const [editing, setEditing] = useState<{id: string; node: MapNode}>();
  const [saving, setSaving] = useState(false);
  const [remove, setRemove] = useState(false);
  const [editError, setEditError] = useState("");
  const canvas = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; y: number; left: number; top: number }>();
  useEffect(() => {
    const observer = new ResizeObserver(entries => setWidth(entries[0].contentRect.width));
    if (canvas.current) observer.observe(canvas.current);
    return () => observer.disconnect();
  }, []);
  const all = useMemo(() => {
    const items: { id: string; node: MapNode; ancestors: string[]; path: string[] }[] = [];
    function visit(nodes: MapNode[], prefix: string, ancestors: string[], path: string[]) {
      nodes.forEach((node, index) => {
        const id = prefix ? `${prefix}.${index}` : String(index);
        items.push({ id, node, ancestors, path: [...path, node.label] });
        visit(node.children, id, [...ancestors, id], [...path, node.label]);
      });
    }
    visit(map.branches, "", [], []);
    return items;
  }, [map]);
  const hits = all.filter(item => `${item.node.label} ${item.node.relation} ${item.node.detail}`.toLowerCase().includes(query.trim().toLowerCase()));
  const reveal = new Set(expanded);
  if (query.trim()) hits.forEach(item => item.ancestors.forEach(id => reveal.add(id)));
  const shown = new Set(query.trim() ? hits.flatMap(item => [...item.ancestors, item.id]) : all.map(item => item.id));
  const items: Item[] = [];
  function children(node: MapNode, id: string) {
    return reveal.has(id) ? node.children.map((child, index) => ({ node: child, id: `${id}.${index}` })).filter(child => shown.has(child.id)) : [];
  }
  function span(node: MapNode, id: string): number {
    const list = children(node, id);
    return Math.max(90, list.reduce((sum, child) => sum + span(child.node, child.id), 0));
  }
  // 左右交替放主题，子树按可见叶子分配高度，父节点对齐子树中线。
  const sides = [0, 1].map(side => map.branches.map((node, index) => ({ node, index })).filter(item => item.index % 2 === side && shown.has(String(item.index))));
  sides.forEach((branches, side) => {
    const direction = side === 0 ? 1 : -1;
    const total = branches.reduce((sum, branch) => sum + span(branch.node, String(branch.index)) + 30, 0);
    let top = -total / 2;
    function layout(node: MapNode, id: string, depth: number, branch: number, center: number, parent?: string, path: string[] = []) {
      const nextPath = [...path, node.label];
      items.push({ id, node, depth, branch, x: direction * depth * 350, y: center, parent, path: nextPath });
      const list = children(node, id);
      let offset = center - span(node, id) / 2;
      list.forEach(child => { const height = span(child.node, child.id); layout(child.node, child.id, depth + 1, branch, offset + height / 2, id, nextPath); offset += height; });
    }
    branches.forEach(branch => { const id = String(branch.index); const height = span(branch.node, id); layout(branch.node, id, 1, branch.index, top + height / 2); top += height + 30; });
  });
  const minX = Math.min(-125, ...items.map(item => item.x - 110)) - 40;
  const maxX = Math.max(125, ...items.map(item => item.x + 110)) + 40;
  const minY = Math.min(-50, ...items.map(item => item.y - 35)) - 50;
  const maxY = Math.max(50, ...items.map(item => item.y + 35)) + 50;
  const w = maxX - minX, h = maxY - minY;
  const scale = Math.min(1, width / w) * zoom;
  const detail = all.find(item => item.id === selected);
  function pick(item: Item) {
    setSelected(item.id);
    setExpanded(previous => { const next = new Set(previous); if (next.has(item.id)) next.delete(item.id); else next.add(item.id); return next; });
  }
  async function saveNode() {
    if (!editing) return;
    setSaving(true); setEditError("");
    function update(nodes: MapNode[], prefix = ""): MapNode[] {
      return nodes.flatMap((node,index) => {
        const id = prefix ? `${prefix}.${index}` : String(index);
        if (id === editing!.id) return remove ? [] : [editing!.node];
        const next = {...node,children:update(node.children,id)};
        if (!prefix && !next.children.length) return [];
        return [next];
      });
    }
    try {
      const next = {...map,branches:update(map.branches)};
      if (!next.branches.length) throw new Error("至少保留一个主题，不能删除整个导图");
      await onChange(next); setEditing(undefined);
    } catch(error) { setEditError(networkMessage(error)); }
    finally { setSaving(false); }
  }
  return <section className="mindmap semantic-map" aria-label="AI 语义思维导图">
    <div className="mindmap-toolbar">
      <input aria-label="搜索概念或关系" placeholder="搜索概念，自动展开所在路径…" value={query} onChange={event => setQuery(event.target.value)} />
      <button className="button secondary" onClick={() => setExpanded(new Set(all.map(item => item.id)))}>展开全部</button>
      <button className="button secondary" onClick={() => { setExpanded(new Set()); setQuery(""); }}>收起分支</button>
      <button className="button secondary" aria-label="缩小" disabled={zoom <= 0.6} onClick={() => setZoom(value => Math.max(0.6, value - 0.2))}>−</button>
      <button className="button secondary" onClick={() => setZoom(1)}>适应宽度</button>
      <button className="button secondary" aria-label="放大" disabled={zoom >= 2.8} onClick={() => setZoom(value => Math.min(2.8, value + 0.2))}>＋</button>
    </div>
    <div className="map-legend"><span>主题 → 核心概念 → 条件与应用</span><span>{all.length} 个节点 · 点击展开，拖动画布{query.trim() ? ` · ${hits.length} 项匹配` : ""}</span></div>
    <div className="mindmap-canvas semantic-canvas" ref={canvas} tabIndex={0} aria-label="导图画布"
      onPointerDown={event => { if (event.pointerType !== "mouse" || (event.target as Element).closest('[role="button"]')) return; drag.current = { x: event.clientX, y: event.clientY, left: event.currentTarget.scrollLeft, top: event.currentTarget.scrollTop }; event.currentTarget.setPointerCapture(event.pointerId); }}
      onPointerMove={event => { if (drag.current) { event.currentTarget.scrollLeft = drag.current.left - (event.clientX - drag.current.x); event.currentTarget.scrollTop = drag.current.top - (event.clientY - drag.current.y); } }}
      onPointerUp={() => { drag.current = undefined; }} onPointerCancel={() => { drag.current = undefined; }}>
      {query.trim() && !hits.length ? <p className="p-6 muted">没有匹配内容，请换个关键词。</p> : <svg width={w * scale} height={Math.max(400, h * scale)} viewBox={`${minX} ${minY} ${w} ${h}`} style={{ minWidth: w * scale }}>
        {items.map(item => {
          const parent = items.find(candidate => candidate.id === item.parent);
          const fromX = parent?.x ?? 0, fromY = parent?.y ?? 0;
          const direction = item.x > 0 ? 1 : -1;
          const startX = fromX + direction * (parent ? 110 : 125), endX = item.x - direction * 110;
          const middle = (startX + endX) / 2;
          return <g key={`edge-${item.id}`}><path d={`M ${startX} ${fromY} C ${middle} ${fromY}, ${middle} ${item.y}, ${endX} ${item.y}`} fill="none" stroke={colors[item.branch]} strokeWidth={item.depth === 1 ? 2.5 : 1.6} opacity={0.6} />
            <text x={middle} y={(fromY + item.y) / 2 - 8} textAnchor="middle" fill={colors[item.branch]} fontSize={11} stroke="#fbfaf6" strokeWidth={4} paintOrder="stroke">{item.node.relation}</text></g>;
        })}
        <rect x={-125} y={-44} width={250} height={88} rx={25} fill="#24463d" />
        <text textAnchor="middle" fill="white" fontSize={17} fontWeight={600}>{wrap(map.title).map((line, index, list) => <tspan key={index} x={0} y={list.length === 1 ? 6 : -6 + index * 25}>{line}</tspan>)}</text>
        {items.map(item => <g key={item.id} role="button" tabIndex={0} className="map-node" aria-label={item.node.label} aria-expanded={item.node.children.length ? reveal.has(item.id) : undefined}
          onClick={() => pick(item)} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); pick(item); } }}>
          <rect x={item.x - 110} y={item.y - 32} width={220} height={64} rx={item.depth === 1 ? 18 : 12} fill={item.depth === 1 ? colors[item.branch] : selected === item.id ? "#edf1e5" : "#ffffff"} stroke={selected === item.id ? "#e56a3c" : colors[item.branch]} strokeWidth={selected === item.id ? 2.5 : 1} />
          <text textAnchor="middle" fill={item.depth === 1 ? "white" : "#263e36"} fontSize={14} fontWeight={item.depth === 1 ? 600 : 400}>{wrap(item.node.label).map((line, index, list) => <tspan key={index} x={item.x} y={item.y + (list.length === 1 ? 5 : -5 + index * 21)}>{line}</tspan>)}</text>
          {item.node.children.length > 0 && <circle cx={item.x + Math.sign(item.x) * 108} cy={item.y} r={10} fill="white" stroke={colors[item.branch]} />}
          {item.node.children.length > 0 && <text x={item.x + Math.sign(item.x) * 108} y={item.y + 4} fontSize={13} textAnchor="middle" fill={colors[item.branch]}>{reveal.has(item.id) ? "−" : "+"}</text>}
        </g>)}
      </svg>}
    </div>
    {detail && <aside className="map-inspector" aria-live="polite"><div><span className="eyebrow">{detail.path.join(" / ")}</span><h3>{detail.node.label}</h3><button className="text-link mt-3" onClick={() => {setEditing({id:detail.id,node:structuredClone(detail.node)});setEditError("");setRemove(false);}}>编辑 / 删除节点</button></div><div><p>{detail.node.detail}</p><SourceRefs deckId={deckId} refs={detail.node.source_refs}/></div></aside>}
    {editing && <Dialog title={remove ? "确认删除这个分支" : "编辑导图节点"} onClose={() => {if (!saving) setEditing(undefined);}}>
      <form id="node-edit" className="content-form" onSubmit={event => {event.preventDefault();void saveNode();}}>
        {remove ? <p className="my-5 leading-7">将移除此节点及其下级节点。删除主题的最后一个概念时，该空主题也会移除；至少需要保留一个主题。</p> : <>
          <label>节点名<input required maxLength={28} value={editing.node.label} onChange={event => setEditing({...editing,node:{...editing.node,label:event.target.value}})}/></label>
          <label>与父节点的关系<input required maxLength={12} value={editing.node.relation} onChange={event => setEditing({...editing,node:{...editing.node,relation:event.target.value}})}/></label>
          <label>解释<textarea required maxLength={180} value={editing.node.detail} onChange={event => setEditing({...editing,node:{...editing.node,detail:event.target.value}})}/></label>
        </>}
      </form>
      {editError && <p className="error-message my-4" role="alert">{editError}</p>}
      <div className="dialog-actions">{!remove && <button className="button secondary" disabled={saving} onClick={() => setRemove(true)}>删除分支</button>}<button className="button secondary" disabled={saving} onClick={() => setEditing(undefined)}>取消</button><button className="button primary" form="node-edit" disabled={saving}>{saving ? "保存中…" : remove ? "确认删除" : "保存修改"}</button></div>
    </Dialog>}
  </section>;
}
