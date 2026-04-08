// Binary WebSocket frames carry raw terminal data (no type wrapper).
// Text WebSocket frames carry JSON control messages:

export type ControlMessage =
  | { type: "resize"; cols: number; rows: number }
  | { type: "pane_size"; cols: number; rows: number }
  | { type: "scrollback"; data: string }
  | { type: "error"; message: string };
