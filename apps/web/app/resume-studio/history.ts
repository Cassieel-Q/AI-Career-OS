import type { StudioDocument, StudioOperation, StudioState } from "./types.ts";

export function findNode(document: StudioDocument, id: string) {
  for (const node of Object.values(document.basics)) if (node.id === id) return node;
  for (const section of document.sections) {
    if (section.title.id === id) return section.title;
    for (const entry of section.entries) {
      for (const node of [entry.title, entry.subtitle, entry.date, entry.location, ...entry.bullets]) {
        if (node.id === id) return node;
      }
    }
  }
  return null;
}

export function inverseOperation(state: StudioState, operation: StudioOperation, next?: StudioState): StudioOperation | null {
  if (operation.type === "set_text") {
    const node = findNode(state.document, operation.node_id);
    return node ? { type: "set_text", node_id: node.id, text: node.text } : null;
  }
  if (operation.type === "omit") return { type: "restore", node_id: operation.node_id };
  if (operation.type === "restore") return { type: "omit", node_id: operation.node_id };
  if (operation.type === "set_template") return { type: "set_template", template_id: state.template_id };
  if (operation.type === "set_language") return { type: "set_language", language: state.language };
  if (operation.type === "add_bullet" && next) {
    const before = state.document.sections.flatMap(section => section.entries).find(entry => entry.id === operation.entry_id);
    const after = next.document.sections.flatMap(section => section.entries).find(entry => entry.id === operation.entry_id);
    const added = after?.bullets.find(bullet => !before?.bullets.some(old => old.id === bullet.id));
    return added ? { type: "omit", node_id: added.id } : null;
  }
  if (operation.type === "add_entry" && next) {
    const before = state.document.sections.find(section => section.id === operation.section_id);
    const after = next.document.sections.find(section => section.id === operation.section_id);
    const added = after?.entries.find(entry => !before?.entries.some(old => old.id === entry.id));
    return added ? { type: "omit", node_id: added.id } : null;
  }
  if (operation.type === "move") {
    const group = state.document.sections.flatMap(section => [section.entries, ...section.entries.map(entry => entry.bullets)])
      .find(items => items.some(item => item.id === operation.node_id));
    if (!group) return null;
    const position = group.findIndex(item => item.id === operation.node_id);
    return { type: "move", node_id: operation.node_id, before_id: group[position + 1]?.id };
  }
  return null;
}

export type HistoryItem = { forward: StudioOperation; inverse: StudioOperation };
export type StudioHistory = { undo: HistoryItem[]; redo: HistoryItem[] };
export function replayOperation(operation: StudioOperation, inverse: StudioOperation): StudioOperation {
  return (operation.type === "add_bullet" || operation.type === "add_entry") && inverse.type === "omit"
    ? { type: "restore", node_id: inverse.node_id } : operation;
}
export const emptyHistory = (): StudioHistory => ({ undo: [], redo: [] });
export const recordHistory = (history: StudioHistory, item: HistoryItem): StudioHistory => ({ undo: [...history.undo, item], redo: [] });
export const undoHistory = (history: StudioHistory): [StudioOperation | null, StudioHistory] => {
  const item = history.undo.at(-1);
  return item ? [item.inverse, { undo: history.undo.slice(0, -1), redo: [...history.redo, item] }] : [null, history];
};
export const redoHistory = (history: StudioHistory): [StudioOperation | null, StudioHistory] => {
  const item = history.redo.at(-1);
  return item ? [item.forward, { undo: [...history.undo, item], redo: history.redo.slice(0, -1) }] : [null, history];
};
