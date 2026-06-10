// ── ADR-021 signal protocol (consume as-is; do not modify) ──
export type SignalType =
  | 'thinking' | 'token' | 'tool_start' | 'tool_end'
  | 'awaiting_confirmation' | 'action_done' | 'error' | 'done';

export interface Signal {
  type: SignalType;
  turnId: string;
  seq: number;
  data: {
    text?: string;
    tool?: string;
    args?: Record<string, unknown>;
    result?: string;
    latency_ms?: number;
    prompt?: string;
    action?: { tool: string; args: Record<string, unknown> };
    message?: string;
  };
}

type SignalHandler = (s: Signal) => void;
type StatusHandler = (status: 'connecting' | 'open' | 'closed' | 'error') => void;

export class MentorForgeSocket {
  private ws: WebSocket | null = null;
  private onSignal: SignalHandler;
  private onStatus: StatusHandler;

  constructor(onSignal: SignalHandler, onStatus: StatusHandler) {
    this.onSignal = onSignal;
    this.onStatus = onStatus;
  }

  connect(wssUrl: string, idToken: string): Promise<void> {
    this.onStatus('connecting');
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(`${wssUrl}?token=${encodeURIComponent(idToken)}`);
      this.ws = ws;
      ws.onopen = () => { this.onStatus('open'); resolve(); };
      ws.onerror = () => { this.onStatus('error'); reject(new Error('WebSocket error')); };
      ws.onclose = () => this.onStatus('closed');
      ws.onmessage = (ev) => {
        try { this.onSignal(JSON.parse(ev.data) as Signal); } catch { /* ignore malformed */ }
      };
    });
  }

  private send(obj: unknown) {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(obj));
  }

  sendMessage(message: string, threadId: string) { this.send({ action: 'sendMessage', payload: { message, threadId } }); }
  confirm() { this.send({ action: 'confirm' }); }
  cancel() { this.send({ action: 'cancel' }); }

  close() { this.ws?.close(); }
}
