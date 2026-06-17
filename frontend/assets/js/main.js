/* JalDrishti main.js — App class definition only.
 * Instantiation is handled by init.js (loaded last).
 */

const API_BASE = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
  ? 'http://localhost:5000'
  : 'https://jal-drishti-sz9o.onrender.com';

class JalDrishti {
  constructor() {
    this.theme = localStorage.getItem('jalTheme') || 'dark';
    this.API = API_BASE;
    this.setupEventBus();
    this.setupTheme();
    this.setupNav();
  }

  setupEventBus() {
    window.eventBus = {
      listeners: {},
      on(e, cb)  { if (!this.listeners[e]) this.listeners[e] = []; this.listeners[e].push(cb); },
      off(e, cb) { if (this.listeners[e]) this.listeners[e] = this.listeners[e].filter(f=>f!==cb); },
      emit(e, d) { (this.listeners[e]||[]).forEach(cb=>cb(d)); }
    };
  }

  setupTheme() {
    document.documentElement.setAttribute('data-theme', this.theme);
    this.updateThemeIcon();
  }

  setupNav() {
    const themeBtn = document.querySelector('.theme-toggle');
    if (themeBtn) themeBtn.addEventListener('click', () => this.toggleTheme());
    document.querySelectorAll('.nav-links a').forEach(link => {
      link.addEventListener('click', e => {
        const href = link.getAttribute('href');
        if (href?.startsWith('#')) {
          const el = document.getElementById(href.substring(1));
          if (el) { e.preventDefault(); el.scrollIntoView({ behavior: 'smooth' }); }
        }
      });
    });
  }

  toggleTheme() {
    this.theme = this.theme === 'dark' ? 'light' : 'dark';
    localStorage.setItem('jalTheme', this.theme);
    document.documentElement.setAttribute('data-theme', this.theme);
    this.updateThemeIcon();
    window.eventBus.emit('theme:changed', { theme: this.theme });
  }

  updateThemeIcon() {
    const btn = document.querySelector('.theme-toggle');
    if (btn) btn.innerHTML = this.theme === 'dark' ? '☀️ Light' : '🌙 Dark';
  }

  async fetch(endpoint, options = {}) {
    const path = endpoint.startsWith('/api') ? endpoint : `/api${endpoint}`;
    const response = await window.fetch(`${API_BASE}${path}`, {
      headers: { 'Content-Type': 'application/json', ...options.headers },
      ...options
    });
    if (!response.ok) throw new Error(`API ${response.status}: ${path}`);
    return response.json();
  }
}
