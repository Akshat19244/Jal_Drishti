/* init.js — Single orchestrator, loaded LAST.
 * Modules that make heavy API calls on init are staggered:
 * - Instant: map, timeline, report, chatbot (lightweight)
 * - On scroll into view: dashboard, explorer, alerts, beaches (heavy)
 * This prevents Flask single-thread queue pile-up on page load.
 */

document.addEventListener('DOMContentLoaded', () => {

  // ── 1. App core ──────────────────────────────────────────────
  window.app = new JalDrishti();

  // ── 2. Lightweight modules — init immediately ────────────────
  window.timelineModule = new TimelineModule();
  window.reportModule   = new ReportModule();
  window.chatbotModule  = new ChatbotModule();
  window.liveModule     = new LiveModule();

  // ── 3. Map — needs Leaflet, fires one API call ───────────────
  window.mapModule = new MapModule();
  window.mapModule.init();

  // ── 4. Heavy modules — load when their section scrolls into view ─
  // This means only ONE heavy request fires at a time.
  const lazyLoad = (sectionId, fn) => {
    const el = document.getElementById(sectionId);
    if (!el) { fn(); return; }  // fallback: load immediately if no element
    const obs = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting) {
        obs.disconnect();
        fn();
      }
    }, { threshold: 0.1 });
    obs.observe(el);
  };

  // Dashboard charts: load when #dash section is visible
  lazyLoad('dash', () => {
    window.dashboardModule = new DashboardModule();
    window.dashboardModule.start();
  });

  // Explorer: load when #explorer section is visible
  lazyLoad('explorer', () => {
    window.explorerModule = new ExplorerModule();
  });

  // Alerts: load when #alerts section is visible
  lazyLoad('alerts', () => {
    window.alertsModule = new AlertsModule();
  });

  // Beaches (cards + heatmap): load when #beaches section is visible
  lazyLoad('beaches', () => {
    window.beachesModule = new BeachesModule();
    window.beachesModule.init();
  });

});
