import { describe, expect, it } from "vitest";
import { deckPath, sessionPath, visibleDecks } from "./library";
import type { LibraryDeck, SavedSession } from "./types";

const first: LibraryDeck = {id:1,title:"高等数学",source_filename:"math.pdf",created_at:"2026-10-20T08:00:00",card_count:10,learned_count:4,wrong_count:2,last_studied_at:"2026-10-22T09:00:00",tags:["期末"],sessions:[],available_outputs:["cards"]};
const second: LibraryDeck = {...first,id:2,title:"物理提纲",source_filename:"physics.pptx",created_at:"2026-10-21T08:00:00",card_count:0,learned_count:0,wrong_count:0,last_studied_at:null,tags:["实验"],available_outputs:["notes","map"]};
describe("课件库", () => {
  it("按标题、原文件名、多个关键词与标签搜索", () => {
    expect(visibleDecks([first,second],"期末 MATH","all","newest").map(item=>item.id)).toEqual([1]);
    expect(visibleDecks([first,second],"不存在","all","recent")).toEqual([]);
    expect(visibleDecks([first,second],"","notes","recent").map(item=>item.id)).toEqual([2]);
    expect(visibleDecks([first,second],"","wrong","recent").map(item=>item.id)).toEqual([1]);
  });
  it("按真实学习时间排序，零卡片资料不产生虚假进度", () => {
    expect(visibleDecks([second,first],"","all","recent").map(item=>item.id)).toEqual([1,2]);
    expect(visibleDecks([first,second],"","all","newest").map(item=>item.id)).toEqual([2,1]);
    expect(visibleDecks([second,first],"","all","progress").map(item=>item.id)).toEqual([1,2]);
  });
  it("资料课件直接进入提纲，错题现场保持独立模式", () => {
    expect(deckPath(second)).toBe('/decks/2/study?tab=notes');
    expect(sessionPath({deck_id:1,mode:"wrong"} as SavedSession)).toBe('/decks/1?mode=wrong');
  });
});
