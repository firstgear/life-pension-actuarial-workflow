import { useEffect, useRef, useState } from 'react';
import {
  Send, Loader2, Code2, ChevronDown, ChevronUp, ExternalLink,
  MessageCircle, Sparkles, RotateCcw, AlertCircle, Database,
} from 'lucide-react';

const BASE = '/api/genie';

type MessageStatus =
  | 'IN_PROGRESS' | 'COMPLETED' | 'FAILED' | 'CANCELLED' | 'QUERY_RESULT_EXPIRED'
  | 'FETCHING_METADATA' | 'ASKING_AI' | 'EXECUTING_QUERY' | 'PENDING_WAREHOUSE' | null;

type GenieAttachment = {
  attachment_id?: string;
  text?: string;
  query?: { query?: string; description?: string; title?: string };
};

type GenieMessage = {
  message_id: string;
  conversation_id: string;
  status: MessageStatus;
  content?: string;
  error?: string;
  attachments?: GenieAttachment[];
};

type QueryResult = {
  has_result: boolean;
  sql?: string;
  title?: string;
  columns?: string[];
  rows?: any[][];
  row_count?: number;
};

type Turn = {
  role: 'user' | 'assistant';
  text: string;
  message?: GenieMessage;
  result?: QueryResult;
  error?: string;
};

export default function GenieChat({
  spaceId, fullScreenUrl, suggestions, height = 520, emptyState,
  variant = 'default',
  title = 'AI/BI Genie',
  subtitle = 'Returns tables, charts, SQL queries',
}: {
  spaceId: string;
  fullScreenUrl?: string | null;
  suggestions?: string[];
  height?: number;
  emptyState?: React.ReactNode;
  /** 'default' = purple compact chat; 'card' = blue AI/BI Genie card matching the
   *  screenshot, with full-width suggestion rows and a prominent header. */
  variant?: 'default' | 'card';
  title?: string;
  subtitle?: string;
}) {
  const isCard = variant === 'card';
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [turns, status]);

  const send = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setStatus('sending…');
    setTurns(prev => [...prev, { role: 'user', text: trimmed }]);
    setInput('');

    try {
      // 1. Start or follow-up
      let convId = conversationId;
      let msg: GenieMessage;
      if (!convId) {
        const res = await fetch(`${BASE}/${spaceId}/start`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: trimmed }),
        });
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();
        convId = data.conversation_id;
        setConversationId(convId);
        msg = data.message;
      } else {
        const res = await fetch(`${BASE}/${spaceId}/conversations/${convId}/message`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: trimmed }),
        });
        if (!res.ok) throw new Error(await res.text());
        msg = (await res.json()).message;
      }

      // 2. Poll until terminal
      let final = msg;
      let pollCount = 0;
      while (final.status && !isTerminal(final.status)) {
        pollCount += 1;
        setStatus(humanStatus(final.status));
        await sleep(Math.min(800 + pollCount * 200, 3000));
        const pres = await fetch(`${BASE}/${spaceId}/conversations/${convId}/messages/${final.message_id}`);
        if (!pres.ok) throw new Error(await pres.text());
        final = await pres.json();
      }

      if (final.status === 'FAILED' || final.status === 'CANCELLED') {
        setTurns(prev => [...prev, {
          role: 'assistant',
          text: final.error || `Genie returned ${final.status}.`,
          message: final,
          error: final.error || final.status || 'failed',
        }]);
        return;
      }

      // 3. If the reply carries SQL, fetch the query result
      let result: QueryResult | undefined;
      const hasQuery = (final.attachments || []).some(a => a.query);
      if (hasQuery) {
        try {
          const qres = await fetch(`${BASE}/${spaceId}/conversations/${convId}/messages/${final.message_id}/query-result`);
          if (qres.ok) result = await qres.json();
        } catch (e) {
          // Non-fatal — we still show the text + SQL
        }
      }

      const replyText = assistantText(final) || (hasQuery ? '' : 'Genie returned an empty response.');
      setTurns(prev => [...prev, { role: 'assistant', text: replyText, message: final, result }]);
    } catch (e: any) {
      setTurns(prev => [...prev, {
        role: 'assistant', text: '', error: String(e?.message || e).slice(0, 300),
      }]);
    } finally {
      setBusy(false);
      setStatus(null);
    }
  };

  const reset = () => {
    setConversationId(null);
    setTurns([]);
    setStatus(null);
  };

  const empty = turns.length === 0 && !busy;

  // Per-variant colour tokens so the two styles share one JSX tree
  const theme = isCard
    ? {
        outer:      'bg-white border-blue-200 rounded-xl',
        header:     'px-5 py-4 border-b border-blue-100',
        headerIcon: 'text-blue-600',
        headerText: 'text-blue-700',
        accent:     'text-blue-600',
        btnPrimary: 'bg-blue-600 hover:bg-blue-700',
        focus:      'focus:ring-blue-500 focus:border-blue-500',
        statusText: 'text-blue-600',
        bg:         '',
      }
    : {
        outer:      'bg-white border-purple-200 rounded-lg',
        header:     'bg-purple-50 border-b border-purple-200 px-4 py-2.5',
        headerIcon: 'text-purple-600',
        headerText: 'text-purple-800',
        accent:     'text-purple-600',
        btnPrimary: 'bg-purple-600 hover:bg-purple-700',
        focus:      'focus:ring-purple-500 focus:border-purple-500',
        statusText: 'text-purple-600',
        bg:         'bg-gradient-to-b from-purple-50/30 to-transparent',
      };

  return (
    <div className={`${theme.outer} border overflow-hidden flex flex-col`} style={{ height }}>
      {/* Header — two layouts, same content */}
      <div className={`${theme.header} flex items-center justify-between shrink-0`}>
        {isCard ? (
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-blue-50 flex items-center justify-center">
              <Database className={`w-5 h-5 ${theme.headerIcon}`} />
            </div>
            <div>
              <div className="text-base font-semibold text-blue-700">{title}</div>
              <div className="text-xs text-blue-500">{subtitle}</div>
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <MessageCircle className={`w-4 h-4 ${theme.headerIcon}`} />
            <span className={`text-sm font-semibold ${theme.headerText}`}>Ask Genie</span>
            {conversationId && <span className={`text-[10px] ${theme.accent} font-mono`}>conversation: {conversationId.slice(0, 8)}…</span>}
          </div>
        )}
        <div className="flex items-center gap-3">
          {turns.length > 0 && (
            <button onClick={reset} className={`flex items-center gap-1 text-[11px] ${theme.accent} hover:opacity-80`}>
              <RotateCcw className="w-3 h-3" /> New conversation
            </button>
          )}
          {fullScreenUrl && (
            <a href={fullScreenUrl} target="_blank" rel="noopener noreferrer"
              className={`flex items-center gap-1 text-[11px] ${theme.accent} hover:opacity-80`}>
              Open in Genie <ExternalLink className="w-3 h-3" />
            </a>
          )}
        </div>
      </div>

      {/* Body */}
      <div ref={scrollRef} className={`flex-1 overflow-y-auto ${isCard ? 'p-4 space-y-2' : 'p-4 space-y-3'} ${theme.bg}`}>
        {empty && isCard && suggestions && suggestions.length > 0 && (
          // Card variant: suggestion rows matching the AI/BI Genie screenshot
          <div className="space-y-2">
            {suggestions.map((s, i) => (
              <button key={i} onClick={() => send(s)}
                className="w-full flex items-center gap-3 px-4 py-3 bg-slate-50 hover:bg-blue-50 border border-transparent hover:border-blue-200 rounded-lg text-left transition-colors">
                <MessageCircle className="w-4 h-4 text-blue-400 shrink-0" />
                <span className="text-sm text-gray-800">{s}</span>
              </button>
            ))}
          </div>
        )}

        {empty && !isCard && (
          <div className="text-center text-gray-500 text-sm mt-4">
            {emptyState || <p>Ask a question about this dataset. Genie generates SQL, runs it, and returns a result.</p>}
            {suggestions && suggestions.length > 0 && (
              <div className="flex flex-wrap gap-2 justify-center mt-4">
                {suggestions.map((s, i) => (
                  <button key={i} onClick={() => send(s)}
                    className="flex items-center gap-1 px-3 py-1.5 text-xs bg-white border border-purple-300 rounded-full text-purple-700 hover:bg-purple-50">
                    <Sparkles className="w-3 h-3" /> {s}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {turns.map((t, i) => <TurnBubble key={i} turn={t} />)}

        {busy && (
          <div className={`flex items-center gap-2 text-xs ${theme.statusText} italic`}>
            <Loader2 className="w-3 h-3 animate-spin" />
            {status || 'Genie is thinking…'}
          </div>
        )}
      </div>

      {/* Input */}
      <div className={`${isCard ? 'border-t border-blue-100 p-3' : 'border-t border-gray-200 p-3'} bg-white shrink-0`}>
        <div className="flex items-center gap-2">
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input); } }}
            disabled={busy}
            placeholder={isCard ? 'Ask about your data…' : (conversationId ? 'Follow up…' : 'Ask about this dataset…')}
            className={`flex-1 px-3 py-2 border ${isCard ? 'border-blue-200 rounded-lg' : 'border-gray-300 rounded'} text-sm ${theme.focus} focus:ring-2 outline-none disabled:bg-gray-50`}
          />
          <button onClick={() => send(input)} disabled={busy || !input.trim()}
            className={`${isCard ? 'px-3 py-2 rounded-lg' : 'px-3 py-2 rounded'} ${theme.btnPrimary} text-white text-sm disabled:opacity-50 flex items-center gap-1`}>
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------
// Turn rendering
// --------------------------------------------------------------------------

function TurnBubble({ turn }: { turn: Turn }) {
  if (turn.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="bg-purple-600 text-white rounded-lg rounded-tr-sm px-3 py-2 text-sm max-w-[75%] whitespace-pre-wrap">
          {turn.text}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="bg-white border border-gray-200 rounded-lg rounded-tl-sm px-3 py-2 text-sm max-w-[90%] shadow-sm">
        {turn.error && (
          <div className="flex items-start gap-2 text-red-700 text-xs bg-red-50 border border-red-200 rounded p-2">
            <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
            <span className="whitespace-pre-wrap break-words">{turn.error}</span>
          </div>
        )}
        {turn.text && <div className="text-gray-800 whitespace-pre-wrap">{turn.text}</div>}
        {turn.message && <SqlAttachment message={turn.message} />}
        {turn.result && turn.result.has_result && <ResultTable result={turn.result} />}
      </div>
    </div>
  );
}

function SqlAttachment({ message }: { message: GenieMessage }) {
  const [open, setOpen] = useState(false);
  const sqlAttachment = (message.attachments || []).find(a => a.query);
  if (!sqlAttachment?.query?.query) return null;
  return (
    <div className="mt-2">
      <button onClick={() => setOpen(v => !v)}
        className="flex items-center gap-1 text-[11px] text-purple-600 hover:text-purple-900">
        <Code2 className="w-3 h-3" />
        {open ? 'Hide SQL' : 'Show SQL'}
        {open ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
      </button>
      {open && (
        <pre className="mt-1 bg-gray-900 text-green-200 rounded text-[11px] p-2 overflow-x-auto max-h-64 leading-relaxed whitespace-pre-wrap">
          {sqlAttachment.query.query}
        </pre>
      )}
    </div>
  );
}

function ResultTable({ result }: { result: QueryResult }) {
  const cols = result.columns || [];
  const rows = (result.rows || []).slice(0, 20);
  if (cols.length === 0 || rows.length === 0) return null;
  return (
    <div className="mt-2 border border-gray-200 rounded overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="bg-gray-50 text-gray-600">
            <tr>
              {cols.map(c => (
                <th key={c} className="px-2 py-1 text-left font-medium border-b whitespace-nowrap">{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className="border-b last:border-b-0 hover:bg-gray-50">
                {row.map((v, j) => (
                  <td key={j} className="px-2 py-1 font-mono text-[11px] whitespace-nowrap">
                    {v == null ? <span className="text-gray-400">null</span> : String(v)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {(result.row_count || 0) > rows.length && (
        <div className="px-2 py-1 text-[10px] text-gray-500 bg-gray-50 border-t">
          Showing first {rows.length} of {result.row_count} rows
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------
// Helpers
// --------------------------------------------------------------------------

function isTerminal(s: string): boolean {
  return ['COMPLETED', 'FAILED', 'CANCELLED', 'QUERY_RESULT_EXPIRED'].includes(s);
}

function humanStatus(s: string): string {
  switch (s) {
    case 'FETCHING_METADATA':  return 'understanding your data…';
    case 'ASKING_AI':          return 'Genie is reasoning…';
    case 'EXECUTING_QUERY':    return 'running the SQL…';
    case 'PENDING_WAREHOUSE':  return 'waking the warehouse…';
    case 'IN_PROGRESS':        return 'in progress…';
    default:                   return s.toLowerCase().replace(/_/g, ' ');
  }
}

function assistantText(msg: GenieMessage): string {
  for (const a of msg.attachments || []) {
    if (a.text) return a.text;
  }
  return msg.content || '';
}

function sleep(ms: number) { return new Promise(resolve => setTimeout(resolve, ms)); }
