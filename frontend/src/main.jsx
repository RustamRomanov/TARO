import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import ErrorBoundary from './components/ErrorBoundary';
import './index.css';

if (typeof window !== 'undefined' && window.Telegram?.WebApp) {
  try {
    window.Telegram.WebApp.expand();
    window.Telegram.WebApp.ready();
  } catch (_) {}
}

const rootEl = document.getElementById('root');
if (!rootEl) {
  throw new Error('Не найден элемент #root');
}

ReactDOM.createRoot(rootEl).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);
