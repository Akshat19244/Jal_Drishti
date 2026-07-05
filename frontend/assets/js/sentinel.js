/* JalDrishti Satellite Data Points Module (GEE-powered)
   Displays CDOM, Turbidity, Chlorophyll-a, Kd490 as per-beach data points
   on the Leaflet India map with exceedance limit color coding.
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
    // Load initial data points on the map
    await this.loadDataPoints('cdom', this.currentDate);
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

  async loadDataPoints(parameter = 'cdom', date = null) {
    const mapLoading = document.getElementById('sentinelMapLoading');
    if (mapLoading) {
      mapLoading.textContent = 'Loading satellite data points...';
      mapLoading.style.display = 'block';
    }

    try {
      const params = new URLSearchParams({ parameter });
      if (date) params.append('date', date);
      const response = await app.fetch(`/api/gee/data-points?${params}`);

      if (mapLoading) mapLoading.style.display = 'none';

      if (response.success && response.data) {
        this.dataPoints = response.data.points || [];
        this.renderDataPoints(response.data.parameter);
        this.updateExceedanceSummary(this.dataPoints, parameter);
        this.updateSourceIndicator(response.data.source);
      } else {
        this.showMapError('No satellite data available');
      }
    } catch (e) {
      console.error('[Satellite] Failed to load data points:', e);
      if (mapLoading) {
        mapLoading.textContent = 'Satellite data unavailable (Earth Engine not configured)';
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

  renderDataPoints(parameter) {
    if (!this.sentinelMap || !this.markerLayer) {
      this.initSentinelMap();
    }

    this.markerLayer.clearLayers();

    if (!this.dataPoints || this.dataPoints.length === 0) {
      this.showMapError('No data points found for selected parameter');
      return;
    }

    const bounds = [];
    const paramLabels = {
      'cdom': 'CDOM',
      'turbidity': 'Turbidity Index',
      'chlorophyll': 'Chlorophyll-a',
      'kd490': 'Kd490'
    };
    const paramLabel = paramLabels[parameter] || parameter;

    this.dataPoints.forEach(pt => {
      const { lat, lon, value, name: beach_name, status, limit, unit, style } = pt;
      if (!lat || !lon) return;

      const statusLabel = status === 'exceeded' ? '⚠ EXCEEDS LIMIT' :
                          status === 'moderate' ? 'Moderate' : 'Safe';

      const statusColor = status === 'exceeded' ? '#DC2626' :
                          status === 'moderate' ? '#D97706' : '#16A34A';

      const circle = L.circleMarker([lat, lon], {
        radius: style && style.radius ? style.radius : 8,
        color: statusColor,
        fillColor: statusColor,
        fillOpacity: 0.7,
        weight: 2
      });

      circle.bindPopup(`
        <div style="font-family:monospace;font-size:12px;line-height:1.6;min-width:220px">
          <div style="font-weight:700;font-size:14px;margin-bottom:4px">${beach_name}</div>
          <div style="border-top:1px solid #333;margin:4px 0;padding:4px 0">
            <b>${paramLabel}:</b> ${value.toFixed(4)} ${unit}<br>
            <b>Status:</b> <span style="color:${statusColor};font-weight:700">${statusLabel}</span><br>
            <b>Safe Limit:</b> ${limit} ${unit}
          </div>
          <div style="font-size:10px;color:#888">
            ${status === 'exceeded' ? '⚠ This parameter exceeds the safe limit!' : '✓ Within acceptable range'}
          </div>
        </div>
      `);

      circle.addTo(this.markerLayer);
      bounds.push([lat, lon]);
    });

    if (bounds.length > 0) {
      this.sentinelMap.fitBounds(bounds, { padding: [30, 30] });
    }

    document.getElementById('sentinelMapLoading').style.display = 'none';
  }

  updateExceedanceSummary(points, parameter) {
    const exceeded = points.filter(p => p.status === 'exceeded');
    const safe = points.filter(p => p.status === 'safe');
    const moderate = points.filter(p => p.status === 'moderate');

    // Update the status section in the cards
    const paramDisplayMap = {
      'cdom': { badge: 'cdomBadge', value: 'cdomValue' },
      'turbidity': { badge: 'turbidityBadge', value: 'turbidityValue' },
      'chlorophyll': { badge: 'chlorophyllBadge', value: 'chlorophyllValue' },
      'kd490': { badge: 'kd490Badge', value: 'kd490Value' }
    };

    if (points.length > 0) {
      const avgValue = points.reduce((s, p) => s + p.value, 0) / points.length;
      const display = paramDisplayMap[parameter];
      if (display) {
        const valEl = document.getElementById(display.value);
        if (valEl) {
          valEl.textContent = avgValue.toFixed(3);
        }
        const badgeEl = document.getElementById(display.badge);
        if (badgeEl) {
          let statusText, statusClass;
          if (exceeded.length > points.length * 0.3) {
            statusText = 'High';
            statusClass = 'status-unsafe';
          } else if (moderate.length > points.length * 0.3) {
            statusText = 'Moderate';
            statusClass = 'status-moderate';
          } else {
            statusText = 'Low';
            statusClass = 'status-safe';
          }
          badgeEl.textContent = statusText;
          badgeEl.className = `pred-badge ${statusClass}`;
        }
      }
    }

    // Show exceedance summary in the map container header
    const summaryEl = document.getElementById('exceedanceSummary');
    if (summaryEl) {
      if (exceeded.length > 0) {
        summaryEl.innerHTML = `<span style="color:#DC2626">⚠ ${exceeded.length}/${points.length} beaches exceed safe limit</span>`;
        summaryEl.style.display = 'block';
      } else {
        summaryEl.innerHTML = `<span style="color:#16A34A">✓ All ${points.length} beaches within safe limits</span>`;
        summaryEl.style.display = 'block';
      }
    }
  }

  updateSourceIndicator(source) {
    const indicator = document.getElementById('sentinelDataSource');
    if (indicator) {
      const sourceLabel = source === 'gee' ? 'Google Earth Engine (Sentinel-2)' :
                          source === 'nasa' ? 'NASA Ocean Color (MODIS)' :
                          'Proxy (CPCB correlations)';
      indicator.textContent = sourceLabel;
    }
  }

  updateUI(data) {
    const cdomValue = document.getElementById('cdomValue');
    const cdomBadge = document.getElementById('cdomBadge');
    if (cdomValue) cdomValue.textContent = data.cdom.value;
    if (cdomBadge) {
      cdomBadge.textContent = data.cdom.status;
      cdomBadge.className = `pred-badge ${this.getStatusClass(data.cdom.status)}`;
    }

    const turbValue = document.getElementById('turbidityValue');
    const turbBadge = document.getElementById('turbidityBadge');
    if (turbValue) turbValue.textContent = data.turbidity.value;
    if (turbBadge) {
      turbBadge.textContent = data.turbidity.status;
      turbBadge.className = `pred-badge ${this.getStatusClass(data.turbidity.status)}`;
    }

    const chlorValue = document.getElementById('chlorophyllValue');
    const chlorBadge = document.getElementById('chlorophyllBadge');
    if (chlorValue) chlorValue.textContent = data.chlorophyll.value;
    if (chlorBadge) {
      chlorBadge.textContent = data.chlorophyll.status;
      chlorBadge.className = `pred-badge ${this.getStatusClass(data.chlorophyll.status)}`;
    }

    const kdValue = document.getElementById('kd490Value');
    const kdBadge = document.getElementById('kd490Badge');
    if (kdValue) kdValue.textContent = data.kd490.value;
    if (kdBadge) {
      kdBadge.textContent = data.kd490.status;
      kdBadge.className = `pred-badge ${this.getStatusClass(data.kd490.status)}`;
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
    // Add controls to the section
    const section = document.getElementById('sentinel');
    if (!section) return;

    const container = section.querySelector('div[style*="padding: 0 3rem"]');
    if (!container) return;

    // Check if controls already exist
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
        Load Data
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
          const indexSelect = document.getElementById('sentinelIndexSelect');
          const param = indexSelect ? indexSelect.value : 'cdom';
          this.loadSentinelData(datePicker.value);
          this.loadDataPoints(param, datePicker.value);
        }
      });
    }

    // Index selector triggers data point reload
    const indexSelect = document.getElementById('sentinelIndexSelect');
    if (indexSelect) {
      indexSelect.addEventListener('change', () => {
        this.loadDataPoints(indexSelect.value, this.currentDate);
      });
    }
  }
}
