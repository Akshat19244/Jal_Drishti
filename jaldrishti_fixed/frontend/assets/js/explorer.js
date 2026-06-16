/* JalDrishti Explorer Module — State/Station/River Views */

class ExplorerModule {
  constructor() {
    this.currentView = 'state';
    this.currentPage = 1;
    this.pageSize = 50;
    this.totalPages = 1;
    this.init();
  }

  init() {
    this.setupTabs();
    this.loadStateView();
  }

  setupTabs() {
    document.querySelectorAll('.explorer-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        document.querySelectorAll('.explorer-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        this.currentView = tab.dataset.view;
        this.switchView();
      });
    });
  }

  switchView() {
    document.querySelectorAll('.explorer-view').forEach(v => v.classList.remove('active'));
    document.querySelector(`[data-view-content="${this.currentView}"]`)?.classList.add('active');
    if (this.currentView === 'state') this.loadStateView();
    if (this.currentView === 'station') this.loadStationView();
    if (this.currentView === 'river') this.loadRiverView();
  }

  async loadStateView() {
    const container = document.querySelector('[data-view-content="state"]');
    if (!container) return;
    container.innerHTML = `<div style="color:var(--t3);font-family:var(--mono);font-size:.75rem;padding:1rem">Loading state data...</div>`;
    try {
      // FIX: was '/explorer/state', now '/api/explorer/state'
      const response = await app.fetch('/api/explorer/state');
      if (!response.success || !response.data) return;
      container.innerHTML = `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:.75rem">` +
        response.data.map(state => {
          const color = this.getWQIColor(state.wqi);
          return `
            <div class="state-card" style="background:var(--card);border:1px solid var(--border);border-radius:8px;
              border-left:3px solid ${color};padding:1rem;cursor:pointer"
              onclick="explorerModule.loadStateDetail('${state.state.replace(/'/g,"\\'")}')">
              <div style="font-size:.78rem;font-weight:600;margin-bottom:.4rem">${state.state}</div>
              <div style="font-family:var(--mono);font-size:1.6rem;color:${color};line-height:1;margin:.3rem 0">${state.wqi ? state.wqi.toFixed(1) : '-'}</div>
              <div style="font-family:var(--mono);font-size:.58rem;color:var(--t3)">${state.wqi_class}</div>
              <div style="margin-top:.5rem;height:2px;background:var(--bg3);border-radius:1px">
                <div style="width:${state.unsafe_pct||0}%;height:100%;background:${color};border-radius:1px"></div>
              </div>
              <div style="font-family:var(--mono);font-size:.55rem;color:var(--t3);margin-top:.3rem">${state.unsafe_pct||0}% unsafe · ${state.station_count||0} stations</div>
            </div>`;
        }).join('') + '</div>';
    } catch (error) {
      console.error('[Explorer] State view failed:', error);
      container.innerHTML = `<div style="color:var(--crit);font-family:var(--mono);font-size:.75rem;padding:1rem">⚠ Could not load state data.</div>`;
    }
  }

  async loadStateDetail(stateName) {
    try {
      const response = await app.fetch(`/api/explorer/state/${encodeURIComponent(stateName)}`);
      if (!response.success) return;
      const d = response.data;
      const stats = d.stats;
      alert(`${stateName}\nWQI: ${stats.wqi_avg} (${stats.wqi_class})\nStations: ${stats.stations}\nAvg DO: ${stats.do_avg} mg/L\nAvg BOD: ${stats.bod_avg} mg/L`);
    } catch(e) { console.error(e); }
  }

  async loadStationView() {
    const container = document.querySelector('[data-view-content="station"]');
    if (!container) return;
    container.innerHTML = `<div style="color:var(--t3);font-family:var(--mono);font-size:.75rem;padding:1rem">Loading station data...</div>`;
    try {
      // FIX: was '/explorer/station', now '/api/explorer/station'
      const response = await app.fetch(`/api/explorer/station?page=${this.currentPage}&limit=${this.pageSize}`);
      if (!response.success || !response.data) return;
      const { stations, pagination } = response.data;
      this.totalPages = pagination.pages || 1;

      container.innerHTML = `
        <div style="margin-bottom:.75rem;display:flex;gap:.5rem;align-items:center;flex-wrap:wrap">
          <span style="font-family:var(--mono);font-size:.62rem;color:var(--t3)">${pagination.total.toLocaleString()} stations total</span>
          <div style="margin-left:auto;display:flex;gap:.5rem">
            <button onclick="explorerModule.changePage(-1)" class="yb" ${this.currentPage<=1?'disabled':''}>← Prev</button>
            <span style="font-family:var(--mono);font-size:.62rem;color:var(--t2);padding:4px 8px">
              Page ${this.currentPage} / ${this.totalPages}
            </span>
            <button onclick="explorerModule.changePage(1)" class="yb" ${this.currentPage>=this.totalPages?'disabled':''}>Next →</button>
          </div>
        </div>
        <div style="overflow-x:auto">
          <table style="width:100%;border-collapse:collapse;font-family:var(--mono);font-size:.68rem">
            <thead>
              <tr style="border-bottom:1px solid var(--border)">
                <th style="padding:7px 12px;text-align:left;color:var(--t3);font-weight:400">Station</th>
                <th style="padding:7px 8px;text-align:left;color:var(--t3);font-weight:400">State</th>
                <th style="padding:7px 8px;text-align:left;color:var(--t3);font-weight:400">Basin</th>
                <th style="padding:7px 8px;text-align:right;color:var(--t3);font-weight:400">DO</th>
                <th style="padding:7px 8px;text-align:right;color:var(--t3);font-weight:400">BOD</th>
                <th style="padding:7px 8px;text-align:right;color:var(--t3);font-weight:400">WQI</th>
                <th style="padding:7px 8px;text-align:center;color:var(--t3);font-weight:400">Status</th>
              </tr>
            </thead>
            <tbody>
              ${stations.map((s, i) => {
                const color = this.getWQIColor(s.wqi);
                const bg = i % 2 ? 'rgba(245,240,230,.015)' : 'transparent';
                const basin = s.basin && s.basin !== 'nan' ? s.basin : '-';
                return `<tr style="background:${bg};border-bottom:1px solid rgba(245,240,230,.04)">
                  <td style="padding:7px 12px;color:var(--t2);max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${s.name}">${s.name}</td>
                  <td style="padding:7px 8px;color:var(--t3)">${s.state}</td>
                  <td style="padding:7px 8px;color:var(--t3);max-width:120px;overflow:hidden;text-overflow:ellipsis">${basin}</td>
                  <td style="padding:7px 8px;text-align:right;color:${(s.do||0)<4?'#FCA5A5':'var(--t2)'}">${s.do ?? '-'}</td>
                  <td style="padding:7px 8px;text-align:right;color:${(s.bod||0)>30?'#FCA5A5':(s.bod||0)>10?'#FCD34D':'var(--t2)'}">${s.bod ?? '-'}</td>
                  <td style="padding:7px 8px;text-align:right;font-weight:500;color:${color}">${s.wqi ?? '-'}</td>
                  <td style="padding:7px 8px;text-align:center">
                    <span style="color:${color};font-size:.6rem">${s.wqi_class||''}</span>
                  </td>
                </tr>`;
              }).join('')}
            </tbody>
          </table>
        </div>`;
    } catch (error) {
      console.error('[Explorer] Station view failed:', error);
      container.innerHTML = `<div style="color:var(--crit);font-family:var(--mono);font-size:.75rem;padding:1rem">⚠ Could not load station data.</div>`;
    }
  }

  changePage(delta) {
    const newPage = this.currentPage + delta;
    if (newPage < 1 || newPage > this.totalPages) return;
    this.currentPage = newPage;
    this.loadStationView();
  }

  async loadRiverView() {
    const container = document.querySelector('[data-view-content="river"]');
    if (!container) return;
    container.innerHTML = `<div style="color:var(--t3);font-family:var(--mono);font-size:.75rem;padding:1rem">Loading river data...</div>`;
    try {
      // FIX: was '/explorer/river', now '/api/explorer/river'
      const response = await app.fetch('/api/explorer/river');
      if (!response.success || !response.data) return;

      container.innerHTML = Object.entries(response.data).slice(0, 25).map(([basinName, river]) => {
        const color = this.getWQIColor(river.avg_wqi);
        const display = basinName !== 'nan' ? basinName : 'Unclassified Basin';
        return `
          <div class="accordion-item" style="background:var(--card);border:1px solid var(--border);border-radius:8px;margin-bottom:.5rem;overflow:hidden">
            <div class="accordion-header" style="padding:.9rem 1.1rem;cursor:pointer;display:flex;align-items:center;justify-content:space-between;user-select:none"
              onclick="this.parentElement.querySelector('.accordion-content').classList.toggle('active');this.querySelector('.accordion-toggle').classList.toggle('active')">
              <div>
                <div style="font-weight:600;font-size:.84rem;margin-bottom:.2rem">${display}</div>
                <div style="font-family:var(--mono);font-size:.58rem;color:var(--t3)">${river.station_count} stations · Avg WQI:
                  <span style="color:${color}">${river.avg_wqi ? river.avg_wqi.toFixed(1) : '-'}</span>
                </div>
              </div>
              <div class="accordion-toggle" style="transition:transform .2s;color:var(--t3)">▼</div>
            </div>
            <div class="accordion-content" style="display:none;padding:0 1.1rem .9rem">
              ${river.stations.map(s => {
                const sc = this.getWQIColor(s.wqi);
                return `<div style="display:flex;justify-content:space-between;align-items:center;
                  padding:.45rem 0;border-bottom:1px solid rgba(245,240,230,.04)">
                  <div>
                    <div style="font-size:.75rem;color:var(--t2)">${s.name}</div>
                    <div style="font-family:var(--mono);font-size:.55rem;color:var(--t3)">${s.state}</div>
                  </div>
                  <div style="text-align:right">
                    <div style="font-family:var(--mono);font-size:.88rem;color:${sc}">${s.wqi ? s.wqi.toFixed(1) : '-'}</div>
                    <div style="font-family:var(--mono);font-size:.55rem;color:var(--t3)">${s.wqi_class||''}</div>
                  </div>
                </div>`;
              }).join('')}
            </div>
          </div>`;
      }).join('');

      // Activate accordion CSS toggle
      document.querySelectorAll('.accordion-content').forEach(el => {
        el.style.cssText = 'padding:0 1.1rem .9rem;';
        el.addEventListener('transitionend', () => {});
      });
      // Simple toggle for accordion-content
      document.querySelectorAll('.accordion-header').forEach(hdr => {
        hdr.addEventListener('click', () => {
          const content = hdr.nextElementSibling;
          const isOpen = content.style.display === 'block';
          content.style.display = isOpen ? 'none' : 'block';
        });
      });
    } catch (error) {
      console.error('[Explorer] River view failed:', error);
      container.innerHTML = `<div style="color:var(--crit);font-family:var(--mono);font-size:.75rem;padding:1rem">⚠ Could not load river data.</div>`;
    }
  }

  getWQIColor(wqi) {
    if (!wqi && wqi !== 0) return '#6B645C';
    if (wqi <= 25) return '#16A34A';
    if (wqi <= 50) return '#65A30D';
    if (wqi <= 75) return '#D97706';
    if (wqi <= 90) return '#EA580C';
    return '#DC2626';
  }
}
