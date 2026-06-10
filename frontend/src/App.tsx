import { useCallback, useEffect, useRef, useState } from 'react';
import { AppConfig, loadConfig } from './config';
import { getIdToken, handleRedirectCallback, login, logout } from './auth';
import { MentorForgeSocket, Signal } from './ws';
import { AssistantTurn, ChatItem, applySignal, newAssistantTurn } from './turn';
import { ThinkingDots, ToolChip, ConfirmCard, ThreadPanel, ArtifactPanel } from './components';
import { Thread, Artifact, HistoryMessage, listThreads, getThreadMessages, listArtifacts } from './history';

type Phase = 'loading' | 'unauthenticated' | 'authenticated';
type ConnStatus = 'connecting' | 'open' | 'closed' | 'error';

function historyToItems(msgs: HistoryMessage[]): ChatItem[] {
  return msgs.map((m, i) => {
    if (m.role === 'user') return { kind: 'user', text: m.text };
    return {
      kind: 'assistant' as const,
      turnId: `hist-${i}-${m.ts}`,
      tools: (m.tool_calls ?? []).map(tc => ({
        tool: tc.tool, result: tc.result, latency: tc.latency_ms, done: true,
      })),
      text: m.text,
      status: 'done' as const,
    };
  });
}

export default function App() {
  const [cfg, setCfg]           = useState<AppConfig | null>(null);
  const [phase, setPhase]       = useState<Phase>('loading');
  const [conn, setConn]         = useState<ConnStatus>('connecting');
  const [items, setItems]       = useState<ChatItem[]>([]);
  const [input, setInput]       = useState('');
  const [busy, setBusy]         = useState(false);

  // thread / history state
  const [threads, setThreads]           = useState<Thread[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string>('');
  const [artifacts, setArtifacts]       = useState<Artifact[]>([]);

  // True while listThreads is in-flight; gates send() so activeThreadId is set
  // before the first message is sent. Without this a fast user (or test) can
  // call send() before setActiveThreadId(ts[0]) runs, creating a stray UUID
  // that the auth loader then overwrites — artifacts end up on an orphaned thread.
  const [authLoading, setAuthLoading] = useState(true);

  const sockRef   = useRef<MentorForgeSocket | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // ── boot: config → handle OAuth callback → auth gate ──
  useEffect(() => {
    (async () => {
      const c = await loadConfig();
      setCfg(c);
      try { await handleRedirectCallback(c); } catch (e) { console.error(e); }
      setPhase(getIdToken() ? 'authenticated' : 'unauthenticated');
    })();
  }, []);

  // ── load history on auth, then connect socket ──
  useEffect(() => {
    if (phase !== 'authenticated' || !cfg) return;
    const token = getIdToken();
    if (!token) { setPhase('unauthenticated'); return; }

    setAuthLoading(true);

    // Load thread list; auto-restore most recent thread.
    // setAuthLoading(false) in the finally block unblocks send() — by that
    // point activeThreadId is guaranteed to be set (thread or fresh UUID).
    (async () => {
      try {
        const ts = await listThreads(cfg.historyApiUrl, token);
        setThreads(ts);
        if (ts.length > 0) {
          const latest = ts[0];
          setActiveThreadId(latest.threadId);
          const msgs = await getThreadMessages(cfg.historyApiUrl, token, latest.threadId);
          setItems(historyToItems(msgs));
          const arts = await listArtifacts(cfg.historyApiUrl, token, latest.threadId);
          setArtifacts(arts);
        } else {
          setActiveThreadId(crypto.randomUUID());
        }
      } catch (e) {
        console.error('History load failed:', e);
        setActiveThreadId(crypto.randomUUID());
      } finally {
        setAuthLoading(false);
      }
    })();

    // Connect WebSocket
    const sock = new MentorForgeSocket(onSignal, setConn);
    sockRef.current = sock;
    sock.connect(cfg.wssUrl, token).catch((e) => console.error(e));
    return () => sock.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, cfg]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [items]);

  function onSignal(s: Signal) {
    setItems((prev) => {
      const idx = prev.findIndex((it) => it.kind === 'assistant' && it.turnId === s.turnId);
      if (idx === -1) {
        const t = applySignal(newAssistantTurn(s.turnId), s);
        return [...prev, t];
      }
      const copy = [...prev];
      copy[idx] = applySignal(copy[idx] as AssistantTurn, s);
      return copy;
    });
    if (s.type === 'done' || s.type === 'error' || s.type === 'awaiting_confirmation') {
      if (s.type !== 'awaiting_confirmation') setBusy(false);
      // Refresh artifacts — fires at awaiting_confirmation (all tool_end already done)
      // and again at done/error for anything surfaced after HITL
      if (cfg) {
        const token = getIdToken();
        if (token && activeThreadIdRef.current) {
          listArtifacts(cfg.historyApiUrl, token, activeThreadIdRef.current)
            .then(setArtifacts)
            .catch(() => {});
        }
      }
    }
  }

  // Keep a ref so the signal handler can read the current activeThreadId
  const activeThreadIdRef = useRef(activeThreadId);
  useEffect(() => { activeThreadIdRef.current = activeThreadId; }, [activeThreadId]);

  const connected = conn === 'open';

  function send(text: string) {
    const msg = text.trim();
    if (!msg || busy || authLoading || !connected || !sockRef.current) return;

    const tid = activeThreadId || crypto.randomUUID();
    if (!activeThreadId) setActiveThreadId(tid);

    // Optimistic: add thread to list if it's new
    setThreads(prev => {
      if (prev.some(t => t.threadId === tid)) return prev;
      const now = new Date().toISOString();
      return [{ threadId: tid, title: msg.slice(0, 60), created_at: now, last_active_at: now, msg_count: 0 }, ...prev];
    });

    setItems((prev) => [...prev, { kind: 'user', text: msg }]);
    sockRef.current.sendMessage(msg, tid);
    setInput('');
    setBusy(true);
  }

  function resolveConfirm(turnId: string, action: 'confirm' | 'cancel') {
    setItems((prev) =>
      prev.map((it) =>
        it.kind === 'assistant' && it.turnId === turnId
          ? { ...it, awaiting: undefined, confirmResolved: action === 'confirm' ? 'confirmed' : 'cancelled', status: 'streaming' }
          : it,
      ),
    );
    if (action === 'confirm') sockRef.current?.confirm();
    else sockRef.current?.cancel();
    setBusy(true);
  }

  async function handleSelectThread(threadId: string) {
    if (!cfg) return;
    const token = getIdToken();
    if (!token) return;

    setActiveThreadId(threadId);
    setItems([]);
    setArtifacts([]);
    setBusy(false);

    try {
      const msgs = await getThreadMessages(cfg.historyApiUrl, token, threadId);
      setItems(historyToItems(msgs));
      const arts = await listArtifacts(cfg.historyApiUrl, token, threadId);
      setArtifacts(arts);
    } catch (e) {
      console.error('Load thread failed:', e);
    }
  }

  function handleNewChat() {
    setActiveThreadId(crypto.randomUUID());
    setItems([]);
    setArtifacts([]);
    setBusy(false);
  }

  if (phase === 'loading') return <Centered>Loading…</Centered>;
  if (phase === 'unauthenticated' && cfg) return <Login onLogin={() => login(cfg)} />;

  return (
    <div className="flex h-full overflow-hidden">
      {/* ── Left pane — thread history ── */}
      <ThreadPanel
        threads={threads}
        activeThreadId={activeThreadId}
        onSelect={handleSelectThread}
        onNewChat={handleNewChat}
      />

      {/* ── Center pane — chat ── */}
      <div className="flex flex-1 flex-col min-w-0">
        <Header conn={conn} onLogout={() => cfg && logout(cfg)} />

        <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-6 space-y-5">
          {items.length === 0 && <EmptyState />}
          {items.map((it, i) =>
            it.kind === 'user'
              ? <UserBubble key={i} text={it.text} />
              : <AssistantBubble key={i} turn={it} onResolve={resolveConfirm} />,
          )}
        </div>

        <Composer value={input} onChange={setInput} onSend={() => send(input)} busy={busy || !connected || authLoading} />
      </div>

      {/* ── Right pane — artifacts ── */}
      <ArtifactPanel
        artifacts={artifacts}
        historyApiUrl={cfg?.historyApiUrl ?? ''}
        idToken={getIdToken() ?? ''}
      />
    </div>
  );
}

// ── chrome ──────────────────────────────────────────────────────────────────

function Header({ conn, onLogout }: { conn: ConnStatus; onLogout: () => void }) {
  const dot = conn === 'open' ? 'bg-emerald-400' : conn === 'connecting' ? 'bg-amber-400' : 'bg-rose-500';
  return (
    <header className="flex items-center gap-3 border-b border-slate-800 px-4 py-3">
      <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br from-accent to-accent2 font-bold text-ink text-sm">M</div>
      <div>
        <div className="font-semibold text-slate-100 text-sm">Onboarding Concierge</div>
        <div className="text-xs text-slate-500">MentorForge · reasoning over your org graph</div>
      </div>
      <div className="ml-auto flex items-center gap-3 text-xs text-slate-400">
        <span className={`h-2 w-2 rounded-full ${dot}`} /> {conn}
        <button onClick={onLogout} className="rounded-md border border-slate-700 px-2 py-1 hover:bg-slate-800">Sign out</button>
      </div>
    </header>
  );
}

function EmptyState() {
  return (
    <div className="mt-16 text-center text-slate-400">
      <div className="text-lg text-slate-200">Ask anything to get started.</div>
      <p className="mx-auto mt-2 max-w-md text-sm">
        The assistant reasons over the company knowledge graph — you&apos;ll see exactly which tools it calls and what they return.
      </p>
    </div>
  );
}

function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-accent/15 px-4 py-2.5 text-slate-100">{text}</div>
    </div>
  );
}

function AssistantBubble({ turn, onResolve }: { turn: AssistantTurn; onResolve: (id: string, a: 'confirm' | 'cancel') => void }) {
  return (
    <div className="flex flex-col gap-2">
      {(turn.status === 'thinking' && turn.tools.length === 0 && !turn.text) && <ThinkingDots />}
      {turn.tools.length > 0 && (
        <div className="space-y-1.5">
          {turn.tools.map((a, i) => <ToolChip key={i} a={a} />)}
        </div>
      )}

      {turn.text && (
        <div className="whitespace-pre-wrap rounded-2xl rounded-bl-sm bg-panel px-4 py-3 leading-relaxed text-slate-100">
          {turn.text}
          {turn.status === 'streaming' && <span className="cursor text-accent">▍</span>}
        </div>
      )}

      {turn.awaiting && (
        <ConfirmCard
          prompt={turn.awaiting.prompt}
          onConfirm={() => onResolve(turn.turnId, 'confirm')}
          onCancel={() => onResolve(turn.turnId, 'cancel')}
        />
      )}
      {turn.confirmResolved && !turn.awaiting && !turn.actionDone && (
        <div className="text-xs text-slate-500">{turn.confirmResolved === 'confirmed' ? '✓ confirmed' : 'cancelled'}</div>
      )}

      {turn.actionDone && (
        <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-300">
          ✓ {turn.actionDone}
        </div>
      )}

      {turn.error && (
        <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-300">
          {turn.error}
        </div>
      )}
    </div>
  );
}

function Composer({ value, onChange, onSend, busy }: { value: string; onChange: (v: string) => void; onSend: () => void; busy: boolean }) {
  return (
    <div className="border-t border-slate-800 px-4 py-3">
      <div className="flex items-end gap-2 rounded-2xl border border-slate-700 bg-panel px-3 py-2">
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); onSend(); } }}
          rows={1}
          placeholder={busy ? 'Working…' : 'Ask your onboarding concierge…'}
          disabled={busy}
          className="max-h-32 flex-1 resize-none bg-transparent py-1.5 text-slate-100 placeholder:text-slate-500 focus:outline-none"
        />
        <button
          onClick={onSend}
          disabled={busy || !value.trim()}
          className="rounded-lg bg-accent px-4 py-1.5 text-sm font-medium text-ink disabled:opacity-40 hover:brightness-110"
        >Send</button>
      </div>
    </div>
  );
}

function Login({ onLogin }: { onLogin: () => void }) {
  return (
    <Centered>
      <div className="text-center">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-accent to-accent2 text-2xl font-bold text-ink">M</div>
        <h1 className="text-xl font-semibold text-slate-100">MentorForge</h1>
        <p className="mt-1 text-sm text-slate-400">Onboarding Concierge</p>
        <button onClick={onLogin} className="mt-6 rounded-lg bg-accent px-5 py-2 font-medium text-ink hover:brightness-110">
          Sign in
        </button>
      </div>
    </Centered>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return <div className="flex h-full items-center justify-center text-slate-300">{children}</div>;
}
