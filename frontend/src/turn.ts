import { Signal } from './ws';

export interface ToolActivity {
  tool: string;
  args?: Record<string, unknown>;
  result?: string;
  latency?: number;
  done: boolean;
}

export type TurnStatus = 'thinking' | 'streaming' | 'awaiting' | 'done' | 'error';

export interface AssistantTurn {
  kind: 'assistant';
  turnId: string;
  tools: ToolActivity[];
  text: string;
  status: TurnStatus;
  awaiting?: { prompt: string; action: { tool: string; args: Record<string, unknown> } };
  confirmResolved?: 'confirmed' | 'cancelled';
  actionDone?: string;
  error?: string;
}

export interface UserTurn { kind: 'user'; text: string; }
export type ChatItem = UserTurn | AssistantTurn;

export function newAssistantTurn(turnId: string): AssistantTurn {
  return { kind: 'assistant', turnId, tools: [], text: '', status: 'thinking' };
}

/** Apply one ADR-021 signal to an assistant turn (mutates a copy, returns it). */
export function applySignal(t: AssistantTurn, s: Signal): AssistantTurn {
  const next: AssistantTurn = { ...t, tools: [...t.tools] };
  switch (s.type) {
    case 'thinking':
      if (next.status !== 'streaming') next.status = 'thinking';
      break;
    case 'tool_start':
      next.tools.push({ tool: s.data.tool ?? '?', args: s.data.args, done: false });
      break;
    case 'tool_end': {
      // close the last open activity matching this tool
      for (let i = next.tools.length - 1; i >= 0; i--) {
        if (next.tools[i].tool === s.data.tool && !next.tools[i].done) {
          next.tools[i] = { ...next.tools[i], done: true, result: s.data.result, latency: s.data.latency_ms };
          break;
        }
      }
      break;
    }
    case 'token':
      next.text += s.data.text ?? '';
      next.status = 'streaming';
      break;
    case 'awaiting_confirmation':
      next.awaiting = {
        prompt: s.data.prompt ?? 'Confirm this action?',
        action: s.data.action ?? { tool: '', args: {} },
      };
      next.status = 'awaiting';
      break;
    case 'action_done':
      next.actionDone = s.data.result ?? 'Done.';
      break;
    case 'error':
      next.error = s.data.message ?? 'Something went wrong.';
      next.status = 'error';
      break;
    case 'done':
      if (next.status !== 'error') next.status = 'done';
      break;
  }
  return next;
}
