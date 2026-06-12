/* JalDrishti Dashboard Module — Chart.js Visualizations
 * FIX 1: Charts were blank because all colors were hardcoded dark-theme values.
 *         Now uses CSS variables resolved at runtime so light/dark both work.
 * FIX 2: Race condition - app.fetch() called before window.app ready.
 *         Now waits for 'app:ready' event before making any API calls.
 */

class DashboardModule {
  constructor() {
    this.charts = {};
    this.currentYear = null;
    this.initialized = false;
  }

  // Called by main.js after app is ready
  start() {
    if (this.initialized) return;
    this.initialized = true;
    this.createAllCharts();
    this.loadAllData();
    window.eventBus.on('timeline:yearChange', (data) => {
      this.currentYear = data.year;
      this.refreshChartsFromTimeline();
    });
    window.eventBus.on('theme:changed', () => {
      // Redraw charts with new theme colors
      Object.values(this.charts).forEach(c => { if (c) c.destroy(); });
      this.charts = {};
      this.createAllCharts();
      this.loadAllData();
    });
  }

  // Resolve a CSS variable to its computed value (works in both themes)
  css(varName) {
    return getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
  }

  createAllCharts() {
    // Resolve colors at chart-creation time so they match current theme
    const t2   = this.css('--t2') || '#888';
    const t3   = this.css('--t3') || '#666';
    const bg3  = this.css('--bg3') || '#eee';
    const grid = 'rgba(128,128,128,0.1)';

    // WQI Distribution bar chart
    const wqiCtx = document.getElementById('wqiChart');
    if (wqiCtx) {
      this.charts.wqi = new Chart(wqiCtx, {
        type: 'bar',
        data: {
          labels: ['Excellent', 'Good', 'Moderate', 'Poor', 'Critical'],
          datasets: [{ label: 'Stations', data: [0,0,0,0,0],
            backgroundColor: ['#16A34A99','#65A30D99','#D9770699','#EA580C99','#DC262699'],
            borderColor:     ['#16A34A',  '#65A30D',  '#D97706',  '#EA580C',  '#DC2626'],
            borderWidth: 1, borderRadius: 5, borderSkipped: false }]
        },
        options: { responsive: true, maintainAspectRatio: true,
          plugins: { legend: { display: false } },
          scales: {
            y: { beginAtZero: true, ticks: { color: t3 }, grid: { color: grid } },
            x: { ticks: { color: t3 }, grid: { display: false } }
          }
        }
      });
    }

    // Parameters radar chart
    const paramCtx = document.getElementById('parameterChart');
    if (paramCtx) {
      this.charts.parameter = new Chart(paramCtx, {
        type: 'radar',
        data: {
          labels: ['DO', 'BOD', 'pH dev', 'Turbidity', 'FColi (log)'],
          datasets: [{ label: 'Avg Values', data: [0,0,0,0,0],
            borderColor: '#2255CC', backgroundColor: 'rgba(34,85,204,0.12)',
            fill: true, pointBackgroundColor: '#4F7FFF', pointBorderColor: '#fff' }]
        },
        options: { responsive: true, maintainAspectRatio: true,
          scales: { r: { beginAtZero: true,
            ticks: { color: t3, backdropColor: 'transparent', font: { size: 9 } },
            grid: { color: grid },
            pointLabels: { color: t2, font: { size: 10 } }
          }}
        }
      });
    }

    // National WQI trend line chart
    const trendCtx = document.getElementById('trendChart');
    if (trendCtx) {
      this.charts.trend = new Chart(trendCtx, {
        type: 'line',
        data: { labels: [], datasets: [{
          label: 'National Avg WQI', data: [],
          borderColor: '#2255CC', backgroundColor: 'rgba(34,85,204,0.08)',
          tension: 0.4, fill: true,
          pointBackgroundColor: '#2255CC', pointBorderColor: '#fff', pointRadius: 2
        }]},
        options: { responsive: true, maintainAspectRatio: true,
          plugins: { legend: { labels: { color: t2, font: { size: 10 } } } },
          scales: {
            y: { ticks: { color: t3 }, grid: { color: grid } },
            x: { ticks: { color: t3, maxRotation: 45, font: { size: 8 } }, grid: { color: grid } }
          }
        }
      });
    }
  }

  async loadAllData() {
    await Promise.all([
      this.loadWQIDistribution(),
      this.loadTrendData(),
      this.loadStateComparison(),
    ]);
  }

  async loadWQIDistribution() {
    try {
      const yearParam = this.currentYear ? `?year=${this.currentYear}` : '';
      const response = await app.fetch(`/api/timeline${yearParam}`);
      if (!response.success || !response.data) return;
      const stations = response.data.stations || [];

      const dist = { excellent: 0, good: 0, moderate: 0, poor: 0, critical: 0 };
      const sums = { do: 0, bod: 0, ph: 0, turb: 0, fcol: 0 };
      const cnts = { do: 0, bod: 0, ph: 0, turb: 0, fcol: 0 };

      stations.forEach(s => {
        const w = s.wqi;
        if (w != null) {
          if (w <= 25) dist.excellent++;
          else if (w <= 50) dist.good++;
          else if (w <= 75) dist.moderate++;
          else if (w <= 90) dist.poor++;
          else dist.critical++;
        }
        const add = (k, v) => { if (v != null) { sums[k] += v; cnts[k]++; } };
        add('do', s.do); add('bod', s.bod); add('ph', s.ph);
        add('turb', s.turbidity); add('fcol', s.fcol);
      });

      if (this.charts.wqi) {
        this.charts.wqi.data.datasets[0].data =
          [dist.excellent, dist.good, dist.moderate, dist.poor, dist.critical];
        this.charts.wqi.update();
      }

      if (this.charts.parameter) {
        const avg = k => cnts[k] ? +(sums[k] / cnts[k]).toFixed(2) : 0;
        this.charts.parameter.data.datasets[0].data =
          [avg('do'), avg('bod'), avg('ph'), avg('turb'),
           cnts.fcol ? +(Math.log10(sums.fcol / cnts.fcol + 1)).toFixed(2) : 0];
        this.charts.parameter.update();
      }

      // Update KPI numbers if they exist
      this.updateKPI(stations, dist);
    } catch (e) {
      console.error('[Dashboard] WQI distribution failed:', e);
    }
  }

  async loadTrendData() {
    try {
      const response = await app.fetch('/api/timeline/trend');
      if (!response.success || !response.data || !this.charts.trend) return;
      const years = Object.keys(response.data).sort();
      this.charts.trend.data.labels = years;
      this.charts.trend.data.datasets[0].data = years.map(y => response.data[y]);
      this.charts.trend.update();
    } catch (e) {
      console.error('[Dashboard] Trend data failed:', e);
    }
  }

  async loadStateComparison() {
    try {
      const response = await app.fetch('/api/explorer/state');
      if (!response.success || !response.data) return;
      this.createStateChart(response.data);
    } catch (e) {
      console.error('[Dashboard] State comparison failed:', e);
    }
  }

  createStateChart(statesData) {
    const ctx = document.getElementById('stateChart');
    if (!ctx) return;
    if (this.charts.state) { this.charts.state.destroy(); }

    const t3  = this.css('--t3') || '#666';
    const t2  = this.css('--t2') || '#888';
    const grid = 'rgba(128,128,128,0.1)';

    const sorted = [...statesData].sort((a, b) => b.wqi - a.wqi).slice(0, 12);
    this.charts.state = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: sorted.map(s => s.state),
        datasets: [{ label: 'Avg WQI', data: sorted.map(s => s.wqi),
          backgroundColor: sorted.map(s =>
            s.wqi > 75 ? 'rgba(220,38,38,.65)' :
            s.wqi > 50 ? 'rgba(234,88,12,.65)' : 'rgba(101,163,13,.65)'),
          borderColor: sorted.map(s =>
            s.wqi > 75 ? '#DC2626' : s.wqi > 50 ? '#EA580C' : '#65A30D'),
          borderWidth: 1, borderRadius: 4 }]
      },
      options: { indexAxis: 'y', responsive: true, maintainAspectRatio: true,
        plugins: { legend: { display: false } },
        scales: {
          x: { beginAtZero: true, max: 100,
               ticks: { color: t3 }, grid: { color: grid } },
          y: { ticks: { color: t2, font: { size: 9 } }, grid: { display: false } }
        }
      }
    });
  }

  updateKPI(stations, dist) {
    const total = stations.length;
    if (!total) return;
    const unsafe = stations.filter(s => s.safety === 'Unsafe').length;
    const wqiAvg = stations.reduce((a, s) => a + (s.wqi || 0), 0) / total;
    // Update any KPI elements in the hero/stats strip if they exist
    const el = id => document.getElementById(id);
    if (el('kpiStations'))  el('kpiStations').textContent  = total.toLocaleString();
    if (el('kpiUnsafePct')) el('kpiUnsafePct').textContent = `${(unsafe/total*100).toFixed(1)}%`;
    if (el('kpiWQIAvg'))    el('kpiWQIAvg').textContent    = wqiAvg.toFixed(1);
  }

  async refreshChartsFromTimeline() {
    await this.loadWQIDistribution();
  }
}
