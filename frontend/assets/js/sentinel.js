/* JalDrishti Sentinel-2 Module */

class SentinelModule {
  constructor() {
    this.currentDate = null;
    this.sentinelMap = null;
    this.currentLayer = null;
    this.init();
  }

  async init() {
    await this.loadSentinelData();
    this.setupEventListeners();
    this.initSentinelMap();
  }

  async loadSentinelData(date = null) {
    try {
      const params = date ? `?date=${date}` : '';
      const response = await app.fetch(`/api/sentinel/indices${params}`);
      
      if (response.success && response.data) {
        this.updateUI(response.data);
        this.currentDate = response.data.date;
        // Load spatial map data
        await this.loadSpatialMap(date);
      }
    } catch (e) {
      console.error('[Sentinel] Failed to load data:', e);
    }
  }

  async loadSpatialMap(date = null) {
    try {
      const params = date ? `?date=${date}&return_image=true` : '?return_image=true';
      const loadingEl = document.getElementById('sentinelMapLoading');
      if (loadingEl) loadingEl.style.display = 'block';
      
      const response = await app.fetch(`/api/sentinel/indices${params}`);
      
      if (response.success && response.data && response.data.image_url) {
        this.displaySpatialMap(response.data);
      }
      
      if (loadingEl) loadingEl.style.display = 'none';
    } catch (e) {
      console.error('[Sentinel] Failed to load spatial map:', e);
      const loadingEl = document.getElementById('sentinelMapLoading');
      if (loadingEl) {
        loadingEl.textContent = 'Spatial data unavailable (requires API key)';
        loadingEl.style.display = 'block';
      }
    }
  }

  initSentinelMap() {
    const mapEl = document.getElementById('sentinelMap');
    if (!mapEl) return;

    // Initialize Leaflet map for India
    this.sentinelMap = L.map('sentinelMap').setView([20.5937, 78.9629], 5); // India center
    
    // Add dark tile layer
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; OpenStreetMap &copy; CARTO',
      maxZoom: 19
    }).addTo(this.sentinelMap);
  }

  displaySpatialMap(data) {
    if (!this.sentinelMap) return;

    if (this.currentLayer) {
      this.sentinelMap.removeLayer(this.currentLayer);
    }

    const imageBounds = [
      [data.bbox[1], data.bbox[0]],
      [data.bbox[3], data.bbox[2]]
    ];

    const indexSelect = document.getElementById('sentinelIndexSelect');
    const selectedIndex = indexSelect ? indexSelect.value : 'cdom';
    const imageUrl = data.image_url;

    const imgOverlay = L.imageOverlay(imageUrl, imageBounds, {
      opacity: 0.7,
      interactive: true
    });

    // Handle image load error → fallback to coloured rectangle
    imgOverlay.on('error', () => {
      console.warn('[Sentinel] Map image failed to load, using rectangle fallback');
      if (this.currentLayer) this.sentinelMap.removeLayer(this.currentLayer);
      this.currentLayer = L.rectangle(imageBounds, {
        color: this.getColorForIndex(),
        weight: 2,
        fillColor: this.getColorForIndex(),
        fillOpacity: 0.4
      }).addTo(this.sentinelMap);
    });

    this.currentLayer = imgOverlay.addTo(this.sentinelMap);
    this.sentinelMap.fitBounds(imageBounds);
  }

  getColorForIndex() {
    const indexSelect = document.getElementById('sentinelIndexSelect');
    if (!indexSelect) return '#2255CC';
    
    const index = indexSelect.value;
    switch(index) {
      case 'cdom': return '#8B5CF6'; // Purple
      case 'turbidity': return '#F59E0B'; // Orange
      case 'chlorophyll': return '#10B981'; // Green
      case 'kd490': return '#3B82F6'; // Blue
      default: return '#2255CC';
    }
  }

  updateUI(data) {
    // Update CDOM
    const cdomValue = document.getElementById('cdomValue');
    const cdomBadge = document.getElementById('cdomBadge');
    if (cdomValue) cdomValue.textContent = data.cdom.value;
    if (cdomBadge) {
      cdomBadge.textContent = data.cdom.status;
      cdomBadge.className = `pred-badge ${this.getStatusClass(data.cdom.status)}`;
    }

    // Update Turbidity
    const turbValue = document.getElementById('turbidityValue');
    const turbBadge = document.getElementById('turbidityBadge');
    if (turbValue) turbValue.textContent = data.turbidity.value;
    if (turbBadge) {
      turbBadge.textContent = data.turbidity.status;
      turbBadge.className = `pred-badge ${this.getStatusClass(data.turbidity.status)}`;
    }

    // Update Chlorophyll
    const chlorValue = document.getElementById('chlorophyllValue');
    const chlorBadge = document.getElementById('chlorophyllBadge');
    if (chlorValue) chlorValue.textContent = data.chlorophyll.value;
    if (chlorBadge) {
      chlorBadge.textContent = data.chlorophyll.status;
      chlorBadge.className = `pred-badge ${this.getStatusClass(data.chlorophyll.status)}`;
    }

    // Update Kd490
    const kdValue = document.getElementById('kd490Value');
    const kdBadge = document.getElementById('kd490Badge');
    if (kdValue) kdValue.textContent = data.kd490.value;
    if (kdBadge) {
      kdBadge.textContent = data.kd490.status;
      kdBadge.className = `pred-badge ${this.getStatusClass(data.kd490.status)}`;
    }

    // Update data source indicator
    this.updateDataSourceIndicator(data.source);
  }

  getStatusClass(status) {
    switch(status.toLowerCase()) {
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

  updateDataSourceIndicator(source) {
    const indicator = document.getElementById('sentinelDataSource');
    if (indicator) {
      indicator.innerHTML = `${source === 'sentinel_hub' ? 'Live Sentinel-2 (Copernicus)' : 'Synthetic (CPCB correlations)'}`;
    }
  }

  setupEventListeners() {
    // Add date picker for historical data
    const section = document.getElementById('sentinel');
    if (section) {
      const controlsDiv = document.createElement('div');
      controlsDiv.style.cssText = 'display:flex;gap:1rem;align-items:center;margin-bottom:1.5rem;';
      controlsDiv.innerHTML = `
        <label style="font-family:var(--mono);font-size:.7rem;color:var(--t3)">Select Date:</label>
        <input type="date" id="sentinelDatePicker" 
          style="background:var(--bg3);border:1px solid var(--border);color:var(--t1);
          font-family:var(--mono);font-size:.7rem;padding:6px 10px;border-radius:4px">
        <button id="loadSentinelData" style="background:var(--sap);color:#fff;border:none;
          padding:6px 12px;border-radius:4px;cursor:pointer;font-family:var(--mono);font-size:.7rem">
          Load Data
        </button>
      `;
      
      const titleDiv = section.querySelector('div[style*="padding: 0 3rem"]');
      if (titleDiv) {
        titleDiv.insertBefore(controlsDiv, titleDiv.children[2]); // Insert after title
      }

      // Set up event listeners
      const datePicker = document.getElementById('sentinelDatePicker');
      const loadBtn = document.getElementById('loadSentinelData');
      
      if (datePicker && loadBtn) {
        // Set max date to today
        const today = new Date().toISOString().split('T')[0];
        datePicker.max = today;
        datePicker.value = today;

        loadBtn.addEventListener('click', () => {
          if (datePicker.value) {
            this.loadSentinelData(datePicker.value);
          }
        });
      }

      // Index selector for map
      const indexSelect = document.getElementById('sentinelIndexSelect');
      if (indexSelect) {
        indexSelect.addEventListener('change', () => {
          // Reload spatial map with selected index
          this.loadSpatialMap(this.currentDate);
        });
      }
    }
  }
}
