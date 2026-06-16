/* JalDrishti Explorer Module */

class ExplorerModule {
  constructor() {
    this.currentView = 'state';
    this.currentPage = 1;
    this.pageSize = 50;
    this.totalPages = 1;
    this._stateLoaded = false;
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
    if (this.currentView === 'state')   this.loadStateView();
    if (this.currentView === 'station') this.loadStationView();
    if (this.currentView === 'river')   this.loadRiverView();
  }

  async loadStateView(retry = 0) {
    const container = document.querySelector('[data-view-content="state"]');
    if (!container) return;
    container.innerHTML = `<div style="color:var(--t3);font-family:var(--mono);font-size:.75rem;padding:1rem">Loading state data...</div>`;
    try {
      const response = await app.fetch('/api/explorer/state');
      if (!response.success || !response.data) throw new Error('No data');

      container.innerHTML = `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:.75rem">` +
        response.data.map(state => {
          const color = this.wqiColor(state.wqi);
          return `
            <div style="background:var(--card);border:1px solid var(--border);border-radius:8px;
              border-left:3px solid ${color};padding:1rem;cursor:pointer"
              onclick="window.explorerModule.loadStateDetail('${state.state.replace(/'/g,"\\'")}')">
              <div style="font-size:.78rem;font-weight:600;margin-bottom:.4rem;color:var(--t1)">${state.state}</div>
              <div style="font-family:var(--mono);font-size:1.5rem;color:${color};line-height:1;margin:.3rem 0">${state.wqi ? state.wqi.toFixed(1) : '-'}</div>
              <div style="font-family:var(--mono);font-size:.58rem;color:var(--t3)">${state.wqi_class || ''}</div>
              <div style="margin-top:.5rem;height:3px;background:var(--bg3);border-radius:2px">
                <div style="width:${Math.min(state.unsafe_pct||0,100)}%;height:100%;background:${color};border-radius:2px"></div>
              </div>
              <div style="font-family:var(--mono);font-size:.55rem;color:var(--t3);margin-top:.3rem">
                ${state.unsafe_pct||0}% unsafe · ${state.station_count||0} stations
              </div>
            </div>`;
        }).join('') + '</div>';
      this._stateLoaded = true;
    } catch (error) {
      console.error('[Explorer] State view failed:', error);
      if (retry < 3) {
        // Auto-retry up to 3 times with increasing delay
        const delay = (retry + 1) * 2000;
        container.innerHTML = `<div style="color:var(--t3);font-family:var(--mono);font-size:.75rem;padding:1rem">
          Retrying in ${(delay/1000).toFixed(0)}s... (attempt ${retry+1}/3)</div>`;
        setTimeout(() => this.loadStateView(retry + 1), delay);
      } else {
        container.innerHTML = `<div style="color:var(--crit);font-family:var(--mono);font-size:.75rem;padding:1rem">
          ⚠ Could not load state data.
          <button onclick="window.explorerModule.loadStateView(0)"
            style="margin-left:12px;font-family:var(--mono);font-size:.7rem;
            background:var(--sap);color:#fff;border:none;padding:4px 12px;
            border-radius:4px;cursor:pointer">Retry</button>
        </div>`;
      }
    }
  }

  async loadStateDetail(stateName) {
    try {
      const r = await app.fetch(`/api/explorer/state/${encodeURIComponent(stateName)}`);
      if (!r.success) return;
      const d = r.data.stats;
      alert(`${stateName}\nWQI: ${d.wqi_avg} (${d.wqi_class})\nStations: ${d.stations}\nAvg DO: ${d.do_avg} mg/L\nAvg BOD: ${d.bod_avg} mg/L`);
    } catch(e) {}
  }

  async loadStationView(retry = 0) {
    const container = document.querySelector('[data-view-content="station"]');
    if (!container) return;
    container.innerHTML = `<div style="color:var(--t3);font-family:var(--mono);font-size:.75rem;padding:1rem">Loading stations...</div>`;
    try {
      const response = await app.fetch(`/api/explorer/station?page=${this.currentPage}&limit=${this.pageSize}`);
      if (!response.success || !response.data) throw new Error('No data');
      const { stations, pagination } = response.data;
      this.totalPages = pagination.pages || 1;

      container.innerHTML = `
        <div style="margin-bottom:.75rem;display:flex;gap:.5rem;align-items:center;flex-wrap:wrap">
          <span style="font-family:var(--mono);font-size:.62rem;color:var(--t3)">${pagination.total.toLocaleString()} total stations</span>
          <div style="margin-left:auto;display:flex;gap:.5rem;align-items:center">
            <button onclick="window.explorerModule.changePage(-1)"
              style="font-family:var(--mono);font-size:.65rem;background:var(--card);border:1px solid var(--border);
              color:var(--t2);padding:4px 10px;border-radius:4px;cursor:pointer"
              ${this.currentPage<=1?'disabled':''}>← Prev</button>
            <span style="font-family:var(--mono);font-size:.62rem;color:var(--t2)">
              ${this.currentPage} / ${this.totalPages}</span>
            <button onclick="window.explorerModule.changePage(1)"
              style="font-family:var(--mono);font-size:.65rem;background:var(--card);border:1px solid var(--border);
              color:var(--t2);padding:4px 10px;border-radius:4px;cursor:pointer"
              ${this.currentPage>=this.totalPages?'disabled':''}>Next →</button>
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
                <th style="padding:7px 8px;text-align:center;color:var(--t3);font-weight:400">Class</th>
              </tr>
            </thead>
            <tbody>
              ${stations.map((s, i) => {
                const color = this.wqiColor(s.wqi);
                const bg = i%2 ? 'rgba(128,128,128,.04)' : 'transparent';
                const basin = s.basin && s.basin !== 'nan' ? s.basin : '-';
                const doColor = (s.do||99)<4 ? '#DC2626' : 'var(--t2)';
                const bodColor = (s.bod||0)>30 ? '#DC2626' : (s.bod||0)>10 ? '#D97706' : 'var(--t2)';
                return `<tr style="background:${bg};border-bottom:1px solid rgba(128,128,128,.08)">
                  <td style="padding:7px 12px;color:var(--t2);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${s.name}">${s.name}</td>
                  <td style="padding:7px 8px;color:var(--t3)">${s.state}</td>
                  <td style="padding:7px 8px;color:var(--t3);max-width:100px;overflow:hidden;text-overflow:ellipsis">${basin}</td>
                  <td style="padding:7px 8px;text-align:right;color:${doColor}">${s.do ?? '-'}</td>
                  <td style="padding:7px 8px;text-align:right;color:${bodColor}">${s.bod ?? '-'}</td>
                  <td style="padding:7px 8px;text-align:right;font-weight:500;color:${color}">${s.wqi ?? '-'}</td>
                  <td style="padding:7px 8px;text-align:center;font-size:.6rem;color:${color}">${s.wqi_class||''}</td>
                </tr>`;
              }).join('')}
            </tbody>
          </table>
        </div>`;
    } catch (error) {
      if (retry < 2) {
        setTimeout(() => this.loadStationView(retry+1), 2000);
      } else {
        container.innerHTML = `<div style="color:var(--crit);font-family:var(--mono);font-size:.75rem;padding:1rem">
          ⚠ Could not load station data.
          <button onclick="window.explorerModule.loadStationView(0)"
            style="margin-left:12px;font-family:var(--mono);font-size:.7rem;background:var(--sap);
            color:#fff;border:none;padding:4px 12px;border-radius:4px;cursor:pointer">Retry</button></div>`;
      }
    }
  }

  changePage(delta) {
    const newPage = this.currentPage + delta;
    if (newPage < 1 || newPage > this.totalPages) return;
    this.currentPage = newPage;
    this.loadStationView();
  }

  async loadRiverView(retry = 0) {
    const container = document.querySelector('[data-view-content="river"]');
    if (!container) return;
    container.innerHTML = `<div style="color:var(--t3);font-family:var(--mono);font-size:.75rem;padding:1rem">Loading river data...</div>`;
    try {
      const response = await app.fetch('/api/explorer/river');
      if (!response.success || !response.data) throw new Error('No data');

      container.innerHTML = Object.entries(response.data).slice(0, 25).map(([basinName, river]) => {
        const color = this.wqiColor(river.avg_wqi);
        const display = basinName !== 'nan' ? basinName : 'Unclassified';
        return `
          <div style="background:var(--card);border:1px solid var(--border);border-radius:8px;margin-bottom:.5rem;overflow:hidden">
            <div style="padding:.9rem 1.1rem;cursor:pointer;display:flex;align-items:center;
              justify-content:space-between;user-select:none"
              onclick="const c=this.nextElementSibling;c.style.display=c.style.display==='block'?'none':'block'">
              <div>
                <div style="font-weight:600;font-size:.84rem;color:var(--t1);margin-bottom:.2rem">${display}</div>
                <div style="font-family:var(--mono);font-size:.58rem;color:var(--t3)">
                  ${river.station_count} stations · Avg WQI:
                  <span style="color:${color}">${river.avg_wqi ? river.avg_wqi.toFixed(1) : '-'}</span>
                </div>
              </div>
              <span style="color:var(--t3);font-size:.8rem">▼</span>
            </div>
            <div style="display:none;padding:0 1.1rem .9rem">
              ${river.stations.map(s => {
                const sc = this.wqiColor(s.wqi);
                return `<div style="display:flex;justify-content:space-between;align-items:center;
                  padding:.4rem 0;border-bottom:1px solid rgba(128,128,128,.08)">
                  <div>
                    <div style="font-size:.75rem;color:var(--t2)">${s.name}</div>
                    <div style="font-family:var(--mono);font-size:.55rem;color:var(--t3)">${s.state}</div>
                  </div>
                  <div style="text-align:right">
                    <div style="font-family:var(--mono);font-size:.85rem;color:${sc}">${s.wqi ? s.wqi.toFixed(1) : '-'}</div>
                    <div style="font-family:var(--mono);font-size:.55rem;color:var(--t3)">${s.wqi_class||''}</div>
                  </div>
                </div>`;
              }).join('')}
            </div>
          </div>`;
      }).join('');
    } catch (error) {
      if (retry < 2) {
        setTimeout(() => this.loadRiverView(retry+1), 2000);
      } else {
        container.innerHTML = `<div style="color:var(--crit);font-family:var(--mono);font-size:.75rem;padding:1rem">
          ⚠ Could not load river data.
          <button onclick="window.explorerModule.loadRiverView(0)"
            style="margin-left:12px;font-family:var(--mono);font-size:.7rem;background:var(--sap);
            color:#fff;border:none;padding:4px 12px;border-radius:4px;cursor:pointer">Retry</button></div>`;
      }
    }
  }

  wqiColor(wqi) {
    if (!wqi && wqi !== 0) return '#6B645C';
    if (wqi <= 25) return '#16A34A';
    if (wqi <= 50) return '#65A30D';
    if (wqi <= 75) return '#D97706';
    if (wqi <= 90) return '#EA580C';
    return '#DC2626';
  }
}
