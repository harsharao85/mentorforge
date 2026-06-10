// Presentational pieces for the onboarding-assistant chat.
import { useState, useCallback } from 'react';
import { ToolActivity } from './turn';
import { Thread, Artifact, getArtifactUrl } from './history';

const TOOL_LABEL: Record<string, string> = {
  graph_retrieve: 'graph_retrieve',
  graph_traverse: 'graph_traverse',
  explain_path: 'explain_path',
  schedule_meeting: 'schedule_meeting',
};

const TOOL_HINT: Record<string, string> = {
  graph_retrieve: 'retrieving content from the knowledge graph',
  graph_traverse: 'resolving the people to meet',
  explain_path: 'tracing the relationship path',
  schedule_meeting: 'preparing a calendar action',
};

export function ThinkingDots() {
  return (
    <div className="flex items-center gap-2 text-slate-400 text-sm py-1">
      <span>reasoning</span>
      <span className="dot">·</span><span className="dot">·</span><span className="dot">·</span>
    </div>
  );
}

/** A tool-call chip — the GraphRAG inference made visible. */
export function ToolChip({ a }: { a: ToolActivity }) {
  const running = !a.done;
  return (
    <div className="flex items-start gap-2 rounded-lg border border-slate-700/70 bg-panel/70 px-3 py-2 text-sm">
      <span className={`mt-0.5 h-2 w-2 shrink-0 rounded-full ${running ? 'bg-accent animate-pulse' : 'bg-emerald-400'}`} />
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <code className="font-mono text-accent">{TOOL_LABEL[a.tool] ?? a.tool}</code>
          {a.args && Object.keys(a.args).length > 0 && (
            <span className="truncate text-xs text-slate-400">
              {Object.entries(a.args)
                .filter(([k]) => k !== 'top_k' && !k.startsWith('_'))
                .map(([k, v]) => `${k}=${String(v)}`)
                .join('  ')}
            </span>
          )}
          {a.done && typeof a.latency === 'number' && (
            <span className="ml-auto shrink-0 text-[11px] text-slate-500">{a.latency} ms</span>
          )}
        </div>
        <div className="mt-0.5 text-slate-300">
          {a.done ? a.result : <span className="text-slate-500">{TOOL_HINT[a.tool] ?? 'working…'}</span>}
        </div>
      </div>
    </div>
  );
}

export function ConfirmCard({
  prompt, onConfirm, onCancel, resolved,
}: { prompt: string; onConfirm: () => void; onCancel: () => void; resolved?: 'confirmed' | 'cancelled' }) {
  return (
    <div className="rounded-xl border border-accent2/40 bg-accent2/10 px-4 py-3">
      <div className="text-sm text-slate-100">{prompt}</div>
      {!resolved ? (
        <div className="mt-3 flex gap-2">
          <button
            onClick={onConfirm}
            className="rounded-lg bg-accent px-4 py-1.5 text-sm font-medium text-ink hover:brightness-110"
          >Confirm</button>
          <button
            onClick={onCancel}
            className="rounded-lg border border-slate-600 px-4 py-1.5 text-sm text-slate-300 hover:bg-slate-800"
          >Cancel</button>
        </div>
      ) : (
        <div className={`mt-2 text-xs ${resolved === 'confirmed' ? 'text-emerald-400' : 'text-slate-400'}`}>
          {resolved === 'confirmed' ? '✓ confirmed' : 'cancelled'}
        </div>
      )}
    </div>
  );
}

// ── Left pane — thread history ───────────────────────────────────────────────

const SOURCE_LABEL: Record<string, string> = {
  graph_retrieve: 'docs',
  graph_traverse: 'people',
  explain_path:   'path',
};

export function ThreadPanel({
  threads, activeThreadId, onSelect, onNewChat,
}: {
  threads: Thread[];
  activeThreadId: string;
  onSelect: (id: string) => void;
  onNewChat: () => void;
}) {
  return (
    <aside className="flex w-52 shrink-0 flex-col border-r border-slate-800 bg-canvas/60">
      <div className="flex items-center justify-between border-b border-slate-800 px-3 py-3">
        <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Chats</span>
        <button
          onClick={onNewChat}
          className="rounded-md border border-slate-700 px-2 py-0.5 text-xs text-slate-300 hover:bg-slate-800"
        >+ New</button>
      </div>
      <div className="flex-1 overflow-y-auto py-1">
        {threads.length === 0 && (
          <p className="px-3 pt-4 text-xs text-slate-600">No past chats yet.</p>
        )}
        {threads.map((t) => (
          <button
            key={t.threadId}
            onClick={() => onSelect(t.threadId)}
            className={`w-full px-3 py-2 text-left transition-colors ${
              t.threadId === activeThreadId
                ? 'bg-slate-800 text-slate-100'
                : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'
            }`}
          >
            <div className="truncate text-sm leading-snug">{t.title || 'Untitled'}</div>
            <div className="mt-0.5 text-[11px] text-slate-600">
              {t.last_active_at ? new Date(t.last_active_at).toLocaleDateString() : ''}
            </div>
          </button>
        ))}
      </div>
    </aside>
  );
}

// ── Right pane — artifacts ───────────────────────────────────────────────────

type BodyState = 'collapsed' | 'loading' | 'error' | string; // string = loaded body text

export function ArtifactPanel({
  artifacts,
  historyApiUrl,
  idToken,
}: {
  artifacts: Artifact[];
  historyApiUrl: string;
  idToken: string;
}) {
  // Map of artifactId → BodyState. Cards are collapsed by default.
  const [bodies, setBodies] = useState<Record<string, BodyState>>({});

  const handleCardClick = useCallback(async (a: Artifact) => {
    const id = a.artifactId;
    const current = bodies[id];

    // Toggle collapse if body already loaded
    if (current && current !== 'collapsed' && current !== 'loading') {
      setBodies(prev => ({ ...prev, [id]: 'collapsed' }));
      return;
    }
    if (current === 'loading') return;

    // Old items without s3Key: nothing to expand — body is already in preview/content
    if (!a.s3Key) return;

    setBodies(prev => ({ ...prev, [id]: 'loading' }));
    try {
      const url  = await getArtifactUrl(historyApiUrl, idToken, a.s3Key);
      const resp = await fetch(url);
      if (!resp.ok) throw new Error(`S3 ${resp.status}`);
      const text = await resp.text();
      setBodies(prev => ({ ...prev, [id]: text }));
    } catch (err) {
      setBodies(prev => ({ ...prev, [id]: 'error' }));
    }
  }, [bodies, historyApiUrl, idToken]);

  return (
    <aside className="flex w-60 shrink-0 flex-col border-l border-slate-800 bg-canvas/60">
      <div className="border-b border-slate-800 px-3 py-3">
        <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Documents</span>
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-2">
        {artifacts.length === 0 && (
          <p className="px-1 pt-3 text-xs text-slate-600">Documents and people the agent surfaces will appear here.</p>
        )}
        {artifacts.map((a) => {
          const bodyState = bodies[a.artifactId];
          const isExpandable = !!a.s3Key;
          const isOpen = bodyState && bodyState !== 'collapsed' && bodyState !== 'loading';
          const preview = a.preview ?? a.content ?? '';

          return (
            <div
              key={a.artifactId}
              data-testid="artifact-card"
              className={`rounded-lg border border-slate-700/60 bg-panel/60 px-3 py-2.5 ${isExpandable ? 'cursor-pointer hover:border-slate-600' : ''}`}
              onClick={() => isExpandable && handleCardClick(a)}
            >
              <div className="flex items-center gap-1.5 mb-1">
                <span className="rounded bg-accent/15 px-1.5 py-0.5 text-[10px] font-mono text-accent">
                  {SOURCE_LABEL[a.source] ?? a.source}
                </span>
                {isExpandable && (
                  <span className="ml-auto text-[10px] text-slate-600">
                    {bodyState === 'loading' ? '…' : isOpen ? '▲' : '▼'}
                  </span>
                )}
              </div>
              <div className="text-xs font-medium text-slate-200 leading-snug truncate">{a.title}</div>

              {/* Collapsed: preview (first 200 chars) */}
              {!isOpen && bodyState !== 'loading' && (
                <div className="mt-1 text-[11px] text-slate-500 leading-snug line-clamp-3">{preview}</div>
              )}

              {/* Loading spinner */}
              {bodyState === 'loading' && (
                <div className="mt-1 text-[11px] text-slate-500 animate-pulse">Loading…</div>
              )}

              {/* Expanded: full body from S3 */}
              {isOpen && bodyState !== 'error' && (
                <div className="mt-2 max-h-64 overflow-y-auto text-[11px] text-slate-300 leading-relaxed whitespace-pre-wrap">
                  {bodyState as string}
                </div>
              )}

              {/* Error state */}
              {bodyState === 'error' && (
                <div className="mt-1 text-[11px] text-rose-400">Failed to load — tap to retry</div>
              )}
            </div>
          );
        })}
      </div>
    </aside>
  );
}
