import { useMemo, useRef, useState } from "react";
import type { StudyPoint } from "../types";

function lines(text: string, width = 13): string[] {
  const characters = Array.from(text);
  return Array.from({ length: Math.min(3, Math.ceil(characters.length / width)) }, (_, i) =>
    characters.slice(i * width, (i + 1) * width).join("") + (i === 2 && characters.length > width * 3 ? "…" : ""));
}

export default function MindMap({ title, points }: { title: string; points: StudyPoint[] }) {
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [selectedId, setSelectedId] = useState(points[0]?.card_id);
  const [zoom, setZoom] = useState(1);
  const canvas = useRef<HTMLDivElement>(null);
  const visible = useMemo(() => points.filter(point =>
    `${point.title} ${point.key_point} ${point.explanation}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())), [points, query]);
  const selected = visible.find(point => point.card_id === selectedId) ?? visible[0];
  let cursor = 24;
  const rows = visible.map(point => {
    const y = cursor;
    cursor += expanded.has(point.card_id) ? 158 : 82;
    return { point, y };
  });
  const height = Math.max(220, cursor + 24);
  const rootY = Math.min(height / 2, 220);
  function toggle(id: number) {
    setSelectedId(id);
    setExpanded(previous => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }
  return <section className="mindmap" aria-label="交互式复习思维导图">
    <div className="mindmap-toolbar">
      <input aria-label="搜索知识点" placeholder="搜索知识点或解释…" value={query} onChange={event => setQuery(event.target.value)} />
      <button className="button secondary" onClick={() => setExpanded(new Set(visible.map(point => point.card_id)))}>全部展开</button>
      <button className="button secondary" onClick={() => setExpanded(new Set())}>全部折叠</button>
      <button className="button secondary" aria-label="缩小导图" disabled={zoom <= 0.5} onClick={() => setZoom(value => Math.max(0.5, value - 0.15))}>−</button>
      <button className="button secondary" onClick={() => { setZoom(1); canvas.current?.scrollTo({ left: 0, top: 0 }); }}>重置</button>
      <button className="button secondary" aria-label="放大导图" disabled={zoom >= 1.6} onClick={() => setZoom(value => Math.min(1.6, value + 0.15))}>＋</button>
    </div>
    <p className="muted text-sm my-3">点击知识点展开重点并查看解释；可横向、纵向滚动。找到 {visible.length} 个知识点 · {Math.round(zoom * 100)}%</p>
    <div className="mindmap-layout">
      <div className="mindmap-canvas" ref={canvas} tabIndex={0} aria-label="导图画布，可滚动">
        {!visible.length ? <p className="p-6 muted">没有匹配的知识点，请换个关键词。</p> :
          <svg width={980 * zoom} height={height * zoom} viewBox={`0 0 980 ${height}`} aria-label={`${title} 知识结构`}>
            {rows.map(({ point, y }) => <g key={`edge-${point.card_id}`} fill="none" stroke="#b5c5b7" strokeWidth={2}>
              <path d={`M 232 ${rootY} C 280 ${rootY}, 270 ${y + 30}, 312 ${y + 30}`} />
              {expanded.has(point.card_id) && <>
                <path d={`M 536 ${y + 30} C 580 ${y + 30}, 570 ${y + 28}, 612 ${y + 28}`} />
                <path d={`M 536 ${y + 30} C 580 ${y + 30}, 570 ${y + 100}, 612 ${y + 100}`} />
              </>}
            </g>)}
            <rect x={20} y={rootY - 40} width={212} height={80} rx={16} fill="#24463d" />
            <text x={36} y={rootY - 10} fill="white" fontSize={15}>{lines(title, 12).map((line, index) => <tspan x={36} dy={index ? 20 : 0} key={index}>{line}</tspan>)}</text>
            {rows.map(({ point, y }) => <g key={point.card_id}>
              <g role="button" tabIndex={0} aria-label={`${point.title}，${expanded.has(point.card_id) ? "折叠" : "展开"}`} aria-expanded={expanded.has(point.card_id)}
                onClick={() => toggle(point.card_id)} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); toggle(point.card_id); } }} className="map-node">
                <rect x={312} y={y} width={224} height={62} rx={12} fill={selected?.card_id === point.card_id ? "#e6eddb" : "#ffffff"} stroke={point.wrong_count ? "#e6653d" : "#91a787"} />
                <text x={328} y={y + 24} fill="#24463d" fontSize={14}>{lines(point.title).map((line, index) => <tspan x={328} dy={index ? 19 : 0} key={index}>{line}</tspan>)}</text>
                <text x={516} y={y + 34} fill="#24463d" fontSize={18}>{expanded.has(point.card_id) ? "−" : "+"}</text>
              </g>
              {expanded.has(point.card_id) && <>
                <rect x={612} y={y - 4} width={338} height={66} rx={10} fill="#f0f3e8" />
                <text x={627} y={y + 17} fontSize={13} fill="#425c3e">{lines(point.key_point, 23).map((line, index) => <tspan x={627} dy={index ? 18 : 0} key={index}>{line}</tspan>)}</text>
                <g role="button" tabIndex={0} aria-label={`查看${point.title}的解释`} onClick={() => setSelectedId(point.card_id)} onKeyDown={event => { if (event.key === "Enter") setSelectedId(point.card_id); }} className="map-node">
                  <rect x={612} y={y + 78} width={338} height={44} rx={10} fill="#fff8ed" stroke="#e9dac0" />
                  <text x={627} y={y + 105} fontSize={13} fill="#6b5437">查看解释{point.wrong_count ? ` · 答错 ${point.wrong_count} 次` : " · 点击知识点查看右侧详情"}</text>
                </g>
              </>}
            </g>)}
          </svg>}
      </div>
      {selected && <aside className="mindmap-detail" aria-live="polite">
        <span className="eyebrow">当前知识点</span>
        <h3>{selected.title}</h3>
        <strong>{selected.key_point}</strong>
        <p>{selected.explanation}</p>
        {selected.wrong_count > 0 && <><h4>易错补充 · 答错 {selected.wrong_count} 次</h4><p>{selected.clarification}</p></>}
      </aside>}
    </div>
  </section>;
}
