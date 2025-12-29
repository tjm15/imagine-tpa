import React from 'react';

interface ErrorBoundaryState {
  hasError: boolean;
  error?: Error;
  errorInfo?: { componentStack?: string };
}

export class ErrorBoundary extends React.Component<React.PropsWithChildren<{}>, ErrorBoundaryState> {
  constructor(props: React.PropsWithChildren<{}>) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    this.setState({ error, errorInfo });
    // Also log to console for devtools/source maps
    console.error('Render error caught by ErrorBoundary:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen w-full flex items-center justify-center bg-slate-50">
          <div className="max-w-xl w-full bg-white border border-slate-200 rounded-lg shadow-sm p-4">
            <div className="mb-2">
              <h1 className="text-lg font-semibold text-red-700">Something went wrong</h1>
              <p className="text-sm text-slate-600">The UI failed to render. Details below to help diagnose.</p>
            </div>
            {this.state.error && (
              <div className="bg-red-50 border border-red-200 rounded-md p-3 mb-3 text-sm text-red-800">
                <div className="font-mono break-words">{String(this.state.error.message)}</div>
              </div>
            )}
            {this.state.errorInfo?.componentStack && (
              <div className="bg-slate-50 border border-slate-200 rounded-md p-3 text-xs text-slate-700">
                <div className="font-semibold mb-1">Component stack</div>
                <pre className="whitespace-pre-wrap text-[11px] leading-snug">{this.state.errorInfo.componentStack}</pre>
              </div>
            )}
            <div className="mt-3 text-xs text-slate-500">
              <p>Tip: Open devtools and use source maps to jump to the original TSX source. If this error mentions <span className="font-mono">.length</span>, ensure arrays/strings are defined before accessing length.</p>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
