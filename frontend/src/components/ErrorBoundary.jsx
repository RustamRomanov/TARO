import { Component } from 'react';

export default class ErrorBoundary extends Component {
  state = { hasError: false, error: null };

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error('App error:', error, info);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback != null) {
        return this.props.fallback;
      }
      return (
        <div className="min-h-screen bg-[#0b0b1e] flex flex-col items-center justify-center p-6 text-center">
          <p className="text-amber-400 font-cinzel text-lg mb-2">ASTROV</p>
          <p className="text-white/80 text-sm mb-4">Произошла ошибка</p>
          <pre className="text-left text-xs text-red-400/90 bg-black/40 p-4 rounded-xl max-w-full overflow-auto max-h-48">
            {String(this.state.error?.message ?? this.state.error ?? 'Unknown error')}
          </pre>
          <button
            type="button"
            onClick={() => this.setState({ hasError: false, error: null })}
            className="mt-4 px-4 py-2 rounded-xl border border-amber-500/40 text-amber-400 text-sm hover:bg-amber-500/10"
          >
            Повторить
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
