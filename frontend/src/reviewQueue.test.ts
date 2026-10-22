import { expect, it } from "vitest";
import type { Answer, KnowledgeCard } from "./types";
import { removeQueuedCard, replaceQueuedCard } from "./reviewQueue";

const card = (id: number) => ({id,question:"题目",options:["A","B","C","D"],correct_index:0,reexplain:"解释"}) as KnowledgeCard;
const answer: Answer = {selected_index:0,is_correct:true,reexplain:"原解释"};

it("删除回炉卡的全部副本后接着显示原下一张，不跳过其他卡", () => {
  const queue = [card(1),card(2),card(1),card(3),card(4)];
  const result = removeQueuedCard(queue,{0:answer,1:answer,2:answer},2);
  expect(result.queue.map(item => item.id)).toEqual([2,3,4]);
  expect(result.index).toBe(1);
  expect(result.answers).toEqual({0:answer});
  expect(removeQueuedCard([card(1)],{0:answer},0)).toEqual({queue:[],answers:{},index:0});
});

it("只改解释保留答题状态，改题则重置该卡所有副本", () => {
  const queue = [card(1),card(2),card(1)];
  const edited = {...card(1),reexplain:"新解释"};
  const sameQuestion = replaceQueuedCard(queue,{0:answer,1:answer,2:answer},edited);
  expect(sameQuestion.answers[0].reexplain).toBe("新解释");
  expect(sameQuestion.answers[2].reexplain).toBe("新解释");
  const newQuestion = replaceQueuedCard(queue,{0:answer,1:answer,2:answer},{...edited,question:"新题目"});
  expect(newQuestion.answers).toEqual({1:answer});
  expect(newQuestion.queue.filter(item => item.id === 1).every(item => item.question === "新题目")).toBe(true);
});
