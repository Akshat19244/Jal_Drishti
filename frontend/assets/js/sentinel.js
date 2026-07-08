/* JalDrishti Satellite Data Points Module (GEE-powered)
   Displays CDOM, Turbidity, Chlorophyll-a, Kd490 as per-beach data points
   on the Leaflet India map with exceedance limit color coding.
   ALL 4 parameters are shown simultaneously per beach — no proxy/CSV fallback.
*/

class SentinelModule {
  constructor() {
    this.currentDate = null;
    this.sentinelMap = null;
    this.markerLayer = null;
    this.dataPoints = [];
    this.init();
  }

  async init() {
    await this.loadSentinelData();
    this.initSentinelMap();
    this.setupEventListeners();
    await this.loadDataPoints(this.currentDate);
  }

  async loadSentinelData(date = null) {
    try {
      const params = date ? `?date=${date}` : '';
      const response = await app.fetch(`/api/sentinel/indices${params}`);

      if (response.success && response.data) {
        this.updateUI(response.data);
        this.currentDate = response.data.date;
      }
    } catch (e) {
      console.error('[Satellite] Failed to load data:', e);
    }
  }

  async loadDataPoints(date = null) {
    const mapLoading = document.getElementById('sentinelMapLoading');
    if (mapLoading) {
      mapLoading.textContent = 'Loading Landsat live data points...';
      mapLoading.style.display = 'block';
      mapLoading.style.color = 'var(--t3)';
    }

    try {
      const params = new URLSearchParams();
      if (date) params.append('date', date);
      const response = await app.fetch(`/api/gee/data-points?${params}`);

      if (mapLoading) mapLoading.style.display = 'none';

      if (response.success && response.data) {
        this.dataPoints = response.data.points || [];
        this.renderDataPoints();
        this.updateAllCards();
        this.updateSourceIndicator(response.data.source, response.data.data_year, response.data.description);
      } else {
        this.showMapError(response.error || 'No live satellite data available');
      }
    } catch (e) {
      console.error('[Satellite] Failed to load data points:', e);
      if (mapLoading) {
        mapLoading.textContent = 'Landsat data unavailable (Earth Engine not configured)';
        mapLoading.style.display = 'block';
        mapLoading.style.color = '#DC2626';
      }
    }
  }

  initSentinelMap() {
    const mapEl = document.getElementById('sentinelMap');
    if (!mapEl) return;

    this.sentinelMap = L.map('sentinelMap').setView([20.5937, 78.9629], 5);

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; OpenStreetMap &copy; CARTO',
      maxZoom: 19
    }).addTo(this.sentinelMap);

    this.markerLayer = L.layerGroup().addTo(this.sentinelMap);
  }

  renderDataPoints() {
    if (!this.sentinelMap || !this.markerLayer) {
      this.initSentinelMap();
    }

    this.markerLayer.clearLayers();

    if (!this.dataPoints || this.dataPoints.length === 0) {
      this.showMapError('No Landsat data points found for any beach');
      return;
    }

    const bounds = [];
    const paramLabels = {
      'cdom': 'CDOM',
      'turbidity': 'Turbidity Index',
      'chlorophyll': 'Chlorophyll-a',
      'kd490': 'Kd490'
    };

    this.dataPoints.forEach(pt => {
      const { lat, lon, name, indices, overall_status, data_year, style } = pt;
      if (!lat || !lon || !indices) return;

      const statusColor = overall_status === 'exceeded' ? '#DC2626' :
                          overall_status === 'moderate' ? '#D97706' : '#16A34A';
      const statusLabel = overall_status === 'exceeded' ? '⚠ Exceeds Limit' :
                          overall_status === 'moderate' ? 'Moderate' : 'Safe';

      const circle = L.circleMarker([lat, lon], {
        radius: style && style.radius ? style.radius : 8,
        color: statusColor,
        fillColor: statusColor,
        fillOpacity: 0.7,
        weight: 2
      });

      let paramsHtml = '';
      for (const [key, param] of Object.entries(indices)) {
        const clr = param.status === 'exceeded' ? '#DC2626' :
                    param.status === 'moderate' ? '#D97706' : '#16A34A';
        const lbl = paramLabels[key] || key;
        paramsHtml += `<tr>
          <td style="padding:2px 8px 2px 0;color:#aaa">${lbl}</td>
          <td style="padding:2px 8px;font-weight:600;text-align:right">${param.value.toFixed(4)}</td>
          <td style="padding:2px 0 2px 8px;color:${clr}">${param.unit ? param.unit : ''}</td>
          <td style="padding:2px 0;color:${clr};font-weight:600">${param.status}</td>
        </tr>`;
      }

      const satInfo = data_year ? `Landsat ${data_year}` : 'Landsat';
      circle.bindPopup(`
        <div style="font-family:monospace;font-size:12px;line-height:1.6;min-width:280px">
          <div style="font-weight:700;font-size:14px;margin-bottom:4px">${name}</div>
          <div style="border-top:1px solid #333;border-bottom:1px solid #333;margin:4px 0;padding:4px 0">
            <table style="width:100%;font-size:11px;border-collapse:collapse">
              <tr style="color:#888;font-size:10px;border-bottom:1px solid #333">
                <th style="text-align:left;padding:2px 8px 2px 0">Parameter</th>
                <th style="text-align:right;padding:2px 8px">Value</th>
                <th style="text-align:left;padding:2px 8px">Unit</th>
                <th style="text-align:left;padding:2px 0">Status</th>
              </tr>
              ${paramsHtml}
            </table>
          </div>
          <div style="margin-top:4px;padding:4px;background:rgba(255,255,255,0.05);border-radius:4px">
            <span style="color:${statusColor};font-weight:700">Overall: ${statusLabel}</span>
          </div>
          <div style="font-size:10px;color:#0ea5e9;margin-top:4px">🛰 ${satInfo} · 30m resolution</div>
        </div>
      `);

      circle.addTo(this.markerLayer);
      bounds.push([lat, lon]);
    });

    if (bounds.length > 0) {
      this.sentinelMap.fitBounds(bounds, { padding: [30, 30] });
    }

    const loadingEl = document.getElementById('sentinelMapLoading');
    if (loadingEl) loadingEl.style.display = 'none';
  }

  updateAllCards() {
    if (!this.dataPoints || this.dataPoints.length === 0) return;

    const config = {
      cdom:         { valueEl: 'cdomValue',         badgeEl: 'cdomBadge' },
      turbidity:    { valueEl: 'turbidityValue',    badgeEl: 'turbidityBadge' },
      chlorophyll:  { valueEl: 'chlorophyllValue',  badgeEl: 'chlorophyllBadge' },
      kd490:        { valueEl: 'kd490Value',        badgeEl: 'kd490Badge' },
    };

    for (const [param, cfg] of Object.entries(config)) {
      const values = this.dataPoints
        .map(p => p.indices?.[param]?.value)
        .filter(v => v !== undefined && v !== null);
      if (values.length === 0) continue;

      const avg = values.reduce((s, v) => s + v, 0) / values.length;
      const valEl = document.getElementById(cfg.valueEl);
      if (valEl) valEl.textContent = avg.toFixed(3);

      const statuses = this.dataPoints.map(p => p.indices?.[param]?.status);
      const exceeded = statuses.filter(s => s === 'exceeded').length;
      const moderate = statuses.filter(s => s === 'moderate').length;

      const badgeEl = document.getElementById(cfg.badgeEl);
      if (badgeEl) {
        let text, cls;
        if (exceeded > statuses.length * 0.3) {
          text = 'High'; cls = 'status-unsafe';
        } else if (moderate > statuses.length * 0.3) {
          text = 'Moderate'; cls = 'status-moderate';
        } else {
          text = 'Low'; cls = 'status-safe';
        }
        badgeEl.textContent = text;
        badgeEl.className = `pred-badge ${cls}`;
      }
    }

    const summaryEl = document.getElementById('exceedanceSummary');
    if (summaryEl) {
      const exceeded = this.dataPoints.filter(p => p.overall_status === 'exceeded');
      if (exceeded.length > 0) {
        summaryEl.innerHTML = `<span style="color:#DC2626">⚠ ${exceeded.length}/${this.dataPoints.length} beaches exceed safe limit</span>`;
      } else {
        summaryEl.innerHTML = `<span style="color:#16A34A">✓ All ${this.dataPoints.length} beaches within safe limits</span>`;
      }
      summaryEl.style.display = 'block';
    }
  }

  updateSourceIndicator(source, dataYear, description) {
    const indicator = document.getElementById('sentinelDataSource');
    if (indicator) {
      let label = 'Google Earth Engine (Landsat 8/9)';
      if (dataYear) label += ` · ${dataYear}`;
      if (description) label += ` · ${description}`;
      indicator.textContent = label;
    }
  }

  updateUI(data) {
    const map_ = {
      cdom:         { value: 'cdomValue',         badge: 'cdomBadge' },
      turbidity:    { value: 'turbidityValue',    badge: 'turbidityBadge' },
      chlorophyll:  { value: 'chlorophyllValue',  badge: 'chlorophyllBadge' },
      kd490:        { value: 'kd490Value',        badge: 'kd490Badge' },
    };

    for (const [key, el] of Object.entries(map_)) {
      const valEl = document.getElementById(el.value);
      if (valEl && data[key]) valEl.textContent = data[key].value;
      const badgeEl = document.getElementById(el.badge);
      if (badgeEl && data[key]) {
        badgeEl.textContent = data[key].status;
        badgeEl.className = `pred-badge ${this.getStatusClass(data[key].status)}`;
      }
    }
  }

  getStatusClass(status) {
    switch ((status || '').toLowerCase()) {
      case 'low':
      case 'good':
        return 'status-safe';
      case 'moderate':
        return 'status-moderate';
      case 'high':
      case 'poor':
        return 'status-unsafe';
      default:
        return '';
    }
  }

  showMapError(message) {
    const loadingEl = document.getElementById('sentinelMapLoading');
    if (loadingEl) {
      loadingEl.textContent = message;
      loadingEl.style.display = 'block';
      loadingEl.style.color = '#DC2626';
    }
  }

  setupEventListeners() {
    const section = document.getElementById('sentinel');
    if (!section) return;

    const container = section.querySelector('div[style*="padding: 0 3rem"]');
    if (!container) return;

    if (document.getElementById('sentinelDatePicker')) return;

    const controlsDiv = document.createElement('div');
    controlsDiv.style.cssText = 'display:flex;gap:1rem;align-items:center;margin-bottom:1.5rem;flex-wrap:wrap';
    controlsDiv.innerHTML = `
      <label style="font-family:var(--mono);font-size:.7rem;color:var(--t3)">Select Date:</label>
      <input type="date" id="sentinelDatePicker"
        style="background:var(--bg3);border:1px solid var(--border);color:var(--t1);
        font-family:var(--mono);font-size:.7rem;padding:6px 10px;border-radius:4px">
      <button id="loadSatelliteData" style="background:var(--sap);color:#fff;border:none;
        padding:6px 12px;border-radius:4px;cursor:pointer;font-family:var(--mono);font-size:.7rem">
        Load Live Data
      </button>
      <span id="exceedanceSummary" style="font-family:var(--mono);font-size:.7rem;padding:4px 8px;
        background:var(--bg3);border-radius:4px;display:none"></span>
    `;

    const titleDiv = container.querySelector('.section-title');
    if (titleDiv && titleDiv.parentElement) {
      titleDiv.parentElement.insertBefore(controlsDiv, titleDiv.parentElement.children[2]);
    }

    const datePicker = document.getElementById('sentinelDatePicker');
    const loadBtn = document.getElementById('loadSatelliteData');

    if (datePicker && loadBtn) {
      const today = new Date().toISOString().split('T')[0];
      datePicker.max = today;
      datePicker.value = today;

      loadBtn.addEventListener('click', () => {
        if (datePicker.value) {
          this.loadSentinelData(datePicker.value);
          this.loadDataPoints(datePicker.value);
        }
      });
    }

    const indexSelect = document.getElementById('sentinelIndexSelect');
    if (indexSelect) {
      indexSelect.addEventListener('change', () => {
        this.loadSentinelData(this.currentDate);
      });
    }
  }
}
