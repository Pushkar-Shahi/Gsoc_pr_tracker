import React, { Component, ErrorInfo, ReactNode } from 'react';
import { AlertCircle, RefreshCw, Home } from 'lucide-react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
  }

  private handleReload = () => {
    // Clear any corrupted caches
    if ('caches' in window) {
      caches.keys().then((keys) => {
        for (const k of keys) caches.delete(k);
      });
    }
    window.location.reload();
  };

  public render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-slate-50 dark:bg-[#000000] text-slate-900 dark:text-white flex flex-col items-center justify-center p-6 text-center select-none transition-colors duration-200">
          <div className="max-w-md w-full liquid-glass-card rounded-2xl p-6 sm:p-8 shadow-2xl space-y-5">
            <div className="w-12 h-12 rounded-2xl bg-neutral-900 border border-white/20 flex items-center justify-center mx-auto text-white">
              <AlertCircle className="w-6 h-6" />
            </div>

            <div className="space-y-1">
              <h2 className="text-base font-bold text-white tracking-tight">Something went wrong</h2>
              <p className="text-xs text-neutral-400 font-mono">
                {this.state.error?.message || 'An unexpected rendering error occurred'}
              </p>
            </div>

            <div className="flex flex-col gap-2 pt-2">
              <button
                type="button"
                onClick={this.handleReload}
                className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl bg-white text-black font-semibold text-xs hover:bg-neutral-200 transition active:scale-95 shadow-md"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                <span>Reload Application</span>
              </button>

              <button
                type="button"
                onClick={() => {
                  localStorage.clear();
                  window.location.href = '/';
                }}
                className="w-full flex items-center justify-center gap-2 py-2 px-4 rounded-xl bg-neutral-900 text-neutral-300 border border-white/10 font-medium text-xs hover:bg-neutral-800 transition active:scale-95"
              >
                <Home className="w-3.5 h-3.5" />
                <span>Reset Local Cache & Return Home</span>
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
