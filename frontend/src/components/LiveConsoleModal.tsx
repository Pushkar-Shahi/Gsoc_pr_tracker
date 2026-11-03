import React, { useState, useEffect, useRef } from 'react';
import { Terminal, X, Play, Copy, Check, ShieldCheck, Loader2, Pause, ArrowDown } from 'lucide-react';
import { getAuthToken } from '../api';

interface LiveConsoleModalProps {
  isOpen: boolean;
  onClose: () => void;
  taskId: string;
  taskTitle?: string;
  customCommand?: string;
  onFinished?: (passed: boolean) => void;
}

interface LogLine {
  type: 'stdout' | 'stderr' | 'start' | 'done' | 'error';
  text: string;
  timestamp: string;
}

export function LiveConsoleModal({
  isOpen,
  onClose,
  taskId,
  taskTitle,
  customCommand,
  onFinished
}: LiveConsoleModalProps) {
  const [logs, setLogs] = useState<LogLine[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [isPassed, setIsPassed] = useState<boolean | null>(null);
  const [autoscroll, setAutoscroll] = useState(true);
  const [copied, setCopied] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (isOpen && taskId) {
      startStreaming();
    }
    return () => {
      stopStreaming();
    };
  }, [isOpen, taskId]);

  useEffect(() => {
    if (autoscroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs, autoscroll]);

  const stopStreaming = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsRunning(false);
  };

  const startStreaming = async () => {
    stopStreaming();
    setLogs([]);
    setIsRunning(true);
    setIsPassed(null);

    const abortCtrl = new AbortController();
    abortControllerRef.current = abortCtrl;

    const token = getAuthToken();
    const query = customCommand ? `?custom_command=${encodeURIComponent(customCommand)}` : '';
    const url = `/api/v1/streaming/tasks/${taskId}/validation${query}`;

    try {
      const response = await fetch(url, {
        headers: {
          'Authorization': `Bearer ${token || ''}`,
          'Accept': 'text/event-stream'
        },
        signal: abortCtrl.signal
      });

      if (!response.ok || !response.body) {
        throw new Error(`Streaming failed with HTTP ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop() || '';

        for (const part of parts) {
          const trimmed = part.trim();
          if (trimmed.startsWith('data:')) {
            try {
              const data = JSON.parse(trimmed.slice(5).trim());
              if (data.type === 'start') {
                setLogs(prev => [...prev, {
                  type: 'start',
                  text: `$ ${data.command}`,
                  timestamp: data.timestamp
                }]);
              } else if (data.type === 'stdout' || data.type === 'stderr') {
                setLogs(prev => [...prev, {
                  type: data.type,
                  text: data.text,
                  timestamp: data.timestamp || new Date().toISOString()
                }]);
              } else if (data.type === 'done') {
                setIsPassed(data.passed);
                setIsRunning(false);
                setLogs(prev => [...prev, {
                  type: 'done',
                  text: `Process finished with exit code ${data.exit_code} (${data.passed ? 'PASSED' : 'FAILED'})`,
                  timestamp: data.timestamp || new Date().toISOString()
                }]);
                if (onFinished) {
                  onFinished(data.passed);
                }
              } else if (data.type === 'error') {
                setLogs(prev => [...prev, {
                  type: 'error',
                  text: `ERROR: ${data.text}`,
                  timestamp: data.timestamp || new Date().toISOString()
                }]);
              }
            } catch (err) {
              // Ignore partial JSON
            }
          }
        }
      }
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        setLogs(prev => [...prev, {
          type: 'error',
          text: `Stream connection error: ${err.message}`,
          timestamp: new Date().toISOString()
        }]);
        setIsRunning(false);
        setIsPassed(false);
      }
    }
  };

  const handleCopyLogs = () => {
    const raw = logs.map(l => l.text).join('\n');
    navigator.clipboard.writeText(raw);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-black/85 backdrop-blur-md animate-in fade-in duration-200">
      <div 
        className="relative w-full max-w-4xl h-[85vh] flex flex-col bg-[#050505] border border-white/15 rounded-2xl shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Terminal Header */}
        <div className="flex items-center justify-between px-4 py-3 bg-neutral-950 border-b border-white/10 shrink-0">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-3 rounded-full bg-rose-500/80 cursor-pointer hover:opacity-80" onClick={onClose} />
              <div className="w-3 h-3 rounded-full bg-amber-500/80" />
              <div className="w-3 h-3 rounded-full bg-emerald-500/80" />
            </div>
            <div className="flex items-center gap-2">
              <Terminal className="w-4 h-4 text-cyan-400" />
              <span className="font-mono text-xs font-bold text-white tracking-wide">
                Sandboxed Test Fleet Stream
              </span>
              {taskTitle && (
                <span className="hidden sm:inline font-mono text-[11px] text-neutral-400 truncate max-w-xs">
                  — {taskTitle}
                </span>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Status indicator */}
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-neutral-900 border border-white/10 text-[11px] font-mono">
              {isRunning ? (
                <>
                  <Loader2 className="w-3 h-3 text-cyan-400 animate-spin" />
                  <span className="text-cyan-300">Executing...</span>
                </>
              ) : isPassed === true ? (
                <>
                  <ShieldCheck className="w-3 h-3 text-emerald-400" />
                  <span className="text-emerald-300 font-bold">PASSED</span>
                </>
              ) : isPassed === false ? (
                <>
                  <X className="w-3 h-3 text-rose-400" />
                  <span className="text-rose-300 font-bold">FAILED</span>
                </>
              ) : (
                <span className="text-neutral-400">Idle</span>
              )}
            </div>

            {/* Autoscroll toggle */}
            <button
              onClick={() => setAutoscroll(!autoscroll)}
              className={`p-1.5 rounded-lg border text-xs transition ${
                autoscroll 
                  ? 'bg-neutral-800 border-white/20 text-white' 
                  : 'bg-neutral-950 border-white/10 text-neutral-500'
              }`}
              title={autoscroll ? 'Autoscroll Active' : 'Autoscroll Paused'}
            >
              {autoscroll ? <ArrowDown className="w-3.5 h-3.5" /> : <Pause className="w-3.5 h-3.5" />}
            </button>

            {/* Copy button */}
            <button
              onClick={handleCopyLogs}
              className="p-1.5 rounded-lg bg-neutral-900 border border-white/10 hover:bg-neutral-800 text-neutral-300 text-xs transition"
              title="Copy output"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
            </button>

            {/* Rerun button */}
            <button
              onClick={startStreaming}
              disabled={isRunning}
              className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-white text-black font-semibold text-xs hover:bg-neutral-200 disabled:opacity-50 transition"
            >
              <Play className="w-3 h-3" />
              <span>Rerun</span>
            </button>

            {/* Close button */}
            <button
              onClick={onClose}
              className="p-1.5 text-neutral-400 hover:text-white rounded-lg hover:bg-neutral-900 transition"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Terminal Body */}
        <div 
          ref={scrollRef}
          className="flex-1 p-4 overflow-y-auto font-mono text-xs text-neutral-300 space-y-1 selection:bg-cyan-500/30 selection:text-white"
        >
          {logs.length === 0 ? (
            <div className="flex items-center gap-2 text-neutral-500 py-8">
              <Loader2 className="w-4 h-4 animate-spin text-neutral-400" />
              <span>Initializing sandboxed execution container...</span>
            </div>
          ) : (
            logs.map((log, index) => {
              if (log.type === 'start') {
                return (
                  <div key={index} className="text-cyan-400 font-bold py-1 border-b border-white/10">
                    {log.text}
                  </div>
                );
              }
              if (log.type === 'done') {
                return (
                  <div key={index} className={`font-bold py-1.5 border-t border-white/10 mt-2 ${
                    isPassed ? 'text-emerald-400' : 'text-rose-400'
                  }`}>
                    {log.text}
                  </div>
                );
              }
              if (log.type === 'stderr' || log.type === 'error') {
                return (
                  <div key={index} className="text-rose-300 whitespace-pre-wrap">
                    {log.text}
                  </div>
                );
              }
              return (
                <div key={index} className="whitespace-pre-wrap text-neutral-200 leading-relaxed">
                  {log.text}
                </div>
              );
            })
          )}
        </div>

        {/* Terminal Footer */}
        <div className="px-4 py-2 bg-neutral-950 border-t border-white/10 flex items-center justify-between text-[11px] font-mono text-neutral-400 shrink-0">
          <span>Sandbox: Ephemeral Isolated Fleet (2 CPU / 4GB RAM)</span>
          <span>Lines: {logs.length}</span>
        </div>
      </div>
    </div>
  );
}

