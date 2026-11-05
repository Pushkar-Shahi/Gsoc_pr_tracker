import React, { useState, useEffect } from 'react';
import { 
  Cpu, Server, Plus, Trash2, RefreshCw, CheckCircle2, 
  AlertCircle, ShieldCheck, Terminal, Copy, Check, ExternalLink, Zap
} from 'lucide-react';
import { Runner } from '../types';
import { getRunners, registerRunner, deleteRunner } from '../api';

export function RunnersView() {
  const [runners, setRunners] = useState<Runner[]>([]);
  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [showRegisterModal, setShowRegisterModal] = useState(false);
  const [newRunnerName, setNewRunnerName] = useState('');
  const [newRunnerOS, setNewRunnerOS] = useState('macOS (Darwin arm64)');
  const [createdToken, setCreatedToken] = useState<string | null>(null);
  const [copiedToken, setCopiedToken] = useState(false);
  const [isRegistering, setIsRegistering] = useState(false);

  const fetchRunnerList = async () => {
    try {
      const data = await getRunners();
      setRunners(data);
    } catch (err) {
      console.error('Error fetching runners:', err);
    } finally {
      setLoading(false);
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    fetchRunnerList();
    const interval = setInterval(fetchRunnerList, 15000);
    return () => clearInterval(interval);
  }, []);

  const handleRefresh = () => {
    setIsRefreshing(true);
    fetchRunnerList();
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newRunnerName.trim()) return;
    setIsRegistering(true);
    try {
      const result = await registerRunner(newRunnerName.trim(), newRunnerOS);
      setCreatedToken(result.runner_token);
      await fetchRunnerList();
    } catch (err) {
      console.error('Failed to register runner:', err);
    } finally {
      setIsRegistering(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Are you sure you want to deregister and revoke this runner?')) return;
    await deleteRunner(id);
    setRunners(prev => prev.filter(r => r.id !== id));
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedToken(true);
    setTimeout(() => setCopiedToken(false), 2000);
  };

  const onlineCount = runners.filter(r => r.status === 'online').length;
  const runnerBaseUrl = typeof window !== 'undefined' && window.location.port === '5173'
    ? 'http://127.0.0.1:8000'
    : (typeof window !== 'undefined' ? window.location.origin : 'http://127.0.0.1:8000');

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header & Stats Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-5 rounded-2xl bg-[#0c101a] border border-white/10 shadow-xl">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-bold tracking-tight text-white">Hybrid Local Runners</h2>
            <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded-full bg-emerald-950/80 text-emerald-400 border border-emerald-500/30">
              Zero Cloud Compute Cost
            </span>
          </div>
          <p className="text-xs text-neutral-400 mt-1">
            Execute sandboxed tests, worktree preparation, and Git validation directly on your developer machine.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            onClick={handleRefresh}
            disabled={isRefreshing}
            className="flex items-center gap-1.5 h-9 px-3 rounded-xl text-xs font-medium bg-white/5 text-neutral-300 border border-white/10 hover:bg-white/10 hover:text-white transition active:scale-95"
            title="Refresh Runner Status"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>

          <button
            onClick={() => {
              setShowRegisterModal(true);
              setCreatedToken(null);
              setNewRunnerName('');
            }}
            className="flex items-center gap-1.5 h-9 px-3.5 rounded-xl text-xs font-semibold bg-white text-black hover:bg-neutral-200 transition active:scale-95 shadow-md shadow-white/10"
          >
            <Plus className="w-4 h-4" />
            <span>Register Runner</span>
          </button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="p-4 rounded-2xl bg-[#0c101a] border border-white/10 flex items-center justify-between shadow-xl">
          <div>
            <span className="text-[11px] font-mono uppercase text-neutral-400">Online Runners</span>
            <div className="text-2xl font-bold text-white mt-0.5">{onlineCount}</div>
          </div>
          <div className="w-10 h-10 rounded-xl bg-emerald-950/50 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
            <Zap className="w-5 h-5" />
          </div>
        </div>

        <div className="p-4 rounded-2xl bg-[#0c101a] border border-white/10 flex items-center justify-between shadow-xl">
          <div>
            <span className="text-[11px] font-mono uppercase text-neutral-400">Total Registered</span>
            <div className="text-2xl font-bold text-white mt-0.5">{runners.length}</div>
          </div>
          <div className="w-10 h-10 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center text-neutral-300">
            <Server className="w-5 h-5" />
          </div>
        </div>

        <div className="p-4 rounded-2xl bg-[#0c101a] border border-white/10 flex items-center justify-between shadow-xl">
          <div>
            <span className="text-[11px] font-mono uppercase text-neutral-400">Architecture</span>
            <div className="text-sm font-bold text-white mt-1">Hybrid Cloud-to-Local</div>
          </div>
          <div className="w-10 h-10 rounded-xl bg-blue-950/50 border border-blue-500/30 flex items-center justify-center text-blue-400">
            <Cpu className="w-5 h-5" />
          </div>
        </div>
      </div>

      {/* Runners List */}
      <div className="rounded-2xl bg-[#0c101a] border border-white/10 overflow-hidden shadow-xl">
        <div className="px-5 py-4 border-b border-white/10 flex items-center justify-between">
          <span className="text-xs font-bold uppercase tracking-wider text-neutral-300 font-mono">Connected Devices</span>
          <span className="text-[11px] text-neutral-500">Auto-timeout offline threshold: 90s</span>
        </div>

        {loading ? (
          <div className="p-12 text-center text-neutral-500 flex flex-col items-center gap-2">
            <div className="w-6 h-6 border-2 border-white border-t-transparent rounded-full animate-spin" />
            <span className="text-xs">Loading runners...</span>
          </div>
        ) : runners.length === 0 ? (
          <div className="p-12 text-center text-neutral-500">
            <Server className="w-8 h-8 mx-auto mb-2 text-neutral-600" />
            <p className="text-sm font-semibold text-neutral-300">No runners registered yet</p>
            <p className="text-xs text-neutral-500 mt-1 max-w-sm mx-auto">
              Register your laptop or Mac daemon to start offloading worktree tasks and validation runs locally.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-white/5">
            {runners.map((runner) => {
              const isOnline = runner.status === 'online';
              return (
                <div key={runner.id} className="p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 hover:bg-white/[0.02] transition">
                  <div className="flex items-start gap-3.5 min-w-0">
                    <div className="relative mt-1">
                      <div className="w-9 h-9 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center text-neutral-300">
                        <Terminal className="w-4 h-4" />
                      </div>
                      <span className={`absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full border-2 border-[#0c101a] ${
                        isOnline ? 'bg-emerald-400 animate-pulse' : 'bg-neutral-600'
                      }`} />
                    </div>

                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-bold text-sm text-white truncate">{runner.name}</span>
                        <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full border font-semibold ${
                          isOnline 
                            ? 'bg-emerald-950/60 text-emerald-400 border-emerald-500/30' 
                            : 'bg-white/5 text-neutral-400 border-white/10'
                        }`}>
                          {runner.status.toUpperCase()}
                        </span>
                      </div>

                      <div className="flex items-center gap-3 text-xs text-neutral-400 mt-1 flex-wrap font-mono">
                        <span>OS: {runner.os_info || 'Unknown OS'}</span>
                        <span>&bull;</span>
                        <span>ID: {runner.id}</span>
                        {runner.last_heartbeat_at && (
                          <>
                            <span>&bull;</span>
                            <span className="text-neutral-500">
                              Last Heartbeat: {new Date(runner.last_heartbeat_at).toLocaleTimeString()}
                            </span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-3 shrink-0 self-end sm:self-center">
                    {runner.system_stats && (
                      <div className="hidden md:flex items-center gap-3 text-[11px] font-mono px-3 py-1.5 rounded-xl bg-[#05080f] border border-white/10 text-neutral-400">
                        {runner.system_stats.cpu_percent !== undefined && (
                          <span>CPU: {runner.system_stats.cpu_percent}%</span>
                        )}
                        {runner.system_stats.memory_percent !== undefined && (
                          <span>RAM: {runner.system_stats.memory_percent}%</span>
                        )}
                      </div>
                    )}

                    <button
                      onClick={() => handleDelete(runner.id)}
                      className="p-2 rounded-xl text-neutral-400 hover:text-rose-400 hover:bg-rose-950/20 border border-transparent hover:border-rose-500/20 transition"
                      title="Deregister runner"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Registration Modal */}
      {showRegisterModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
          <div className="relative w-full max-w-lg rounded-2xl bg-[#0c101a] border border-white/15 p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-white/10">
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <Plus className="w-4 h-4 text-emerald-400" />
                Register New Hybrid Runner
              </h3>
              <button 
                onClick={() => setShowRegisterModal(false)}
                className="text-neutral-400 hover:text-white text-sm"
              >
                ✕
              </button>
            </div>

            {!createdToken ? (
              <form onSubmit={handleRegister} className="space-y-4 pt-1">
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-neutral-300">Runner Name</label>
                  <input
                    type="text"
                    value={newRunnerName}
                    onChange={(e) => setNewRunnerName(e.target.value)}
                    placeholder="e.g., MacBook Pro M3 Local Worker"
                    required
                    className="w-full px-3.5 py-2.5 rounded-xl bg-[#05080f] border border-white/10 text-white placeholder-neutral-500 text-xs focus:outline-none focus:border-white/30 transition"
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-neutral-300">Platform / Environment</label>
                  <select
                    value={newRunnerOS}
                    onChange={(e) => setNewRunnerOS(e.target.value)}
                    className="w-full px-3.5 py-2.5 rounded-xl bg-[#05080f] border border-white/10 text-white text-xs focus:outline-none focus:border-white/30 transition cursor-pointer"
                  >
                    <option value="macOS (Darwin arm64)" className="bg-[#0c101a] text-white">macOS (Apple Silicon)</option>
                    <option value="macOS (Darwin x86_64)" className="bg-[#0c101a] text-white">macOS (Intel)</option>
                    <option value="Linux (x86_64)" className="bg-[#0c101a] text-white">Linux Ubuntu / Debian</option>
                    <option value="Windows 11 (WSL2)" className="bg-[#0c101a] text-white">Windows (WSL2)</option>
                  </select>
                </div>

                <div className="pt-2 flex items-center justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setShowRegisterModal(false)}
                    className="px-4 py-2 rounded-xl text-xs font-semibold bg-white/5 hover:bg-white/10 text-neutral-300 border border-white/10 transition"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isRegistering || !newRunnerName.trim()}
                    className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold bg-white text-black hover:bg-neutral-200 transition disabled:opacity-50"
                  >
                    {isRegistering ? 'Generating Token...' : 'Generate Token & Register'}
                  </button>
                </div>
              </form>
            ) : (
              <div className="space-y-4 pt-2">
                <div className="p-3 rounded-xl bg-emerald-950/40 border border-emerald-500/30 flex items-start gap-2.5 text-xs text-emerald-300">
                  <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5 text-emerald-400" />
                  <div>
                    <span className="font-bold">Runner registered successfully!</span>
                    <p className="text-[11px] text-emerald-400/80 mt-0.5">
                      Save this runner authentication token. It will not be shown again.
                    </p>
                  </div>
                </div>

                <div className="space-y-1.5">
                  <span className="text-[11px] font-mono uppercase text-neutral-400">Runner Token</span>
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      readOnly
                      value={createdToken}
                      className="w-full px-3 py-2 rounded-xl bg-[#05080f] border border-white/10 text-white font-mono text-xs select-all"
                    />
                    <button
                      onClick={() => copyToClipboard(createdToken)}
                      className="h-9 px-3 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-neutral-200 hover:text-white flex items-center gap-1 text-xs shrink-0 active:scale-95 transition"
                    >
                      {copiedToken ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                      <span>{copiedToken ? 'Copied' : 'Copy'}</span>
                    </button>
                  </div>
                </div>

                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-mono uppercase text-neutral-400">Launch Command</span>
                    <button
                      onClick={() => copyToClipboard(`python3 -m runner.agent --url ${runnerBaseUrl} --token "${createdToken}"`)}
                      className="text-[11px] text-neutral-400 hover:text-white flex items-center gap-1 transition"
                    >
                      <Copy className="w-3 h-3" />
                      <span>Copy Command</span>
                    </button>
                  </div>
                  <div className="p-3 rounded-xl bg-[#05080f] border border-white/10 text-[11px] font-mono text-neutral-300 overflow-x-auto">
                    <code>
                      python3 -m runner.agent --url {runnerBaseUrl} --token "{createdToken}"
                    </code>
                  </div>
                  <p className="text-[10px] text-neutral-500 font-mono">
                    Zero dependencies required. Runs directly with standard Python 3.10+.
                  </p>
                </div>

                <div className="pt-2 flex justify-end">
                  <button
                    onClick={() => setShowRegisterModal(false)}
                    className="px-4 py-2 rounded-xl text-xs font-semibold bg-white text-black hover:bg-neutral-200 transition"
                  >
                    Done
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

