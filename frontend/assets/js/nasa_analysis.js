/* NASA Satellite Analysis Module — River Body Data Points on India Map */

class NASAAnalysisModule {
  constructor() {
    this.currentDate = null;
    this.currentParameter = 'chlorophyll';
    this.dataPoints = [];
    this.heatmapLayer = null;
    this.init();
  }

  init() {
    this.setupUI();
    this.loadAnalysis();
  }

  setupUI() {
    // Add NASA analysis toggle to map
    const mapSection = document.getElementById('map-sec');
    if (mapSection) {
      const controls = document.querySelector('.map-controls');
      if (controls) {
        const nasaToggle = document.createElement('button');
        nasaToggle.id = 'nasaToggle';
        nasaToggle.textContent = '🛰️ NASA Satellite Data';
        nasaToggle.style.cssText = `
          margin-left: 10px;
          padding: 6px 12px;
          background: var(--sap);
          color: white;
          border: none;
          border-radius: 4px;
          cursor: pointer;
          font-family: var(--mono);
          font-size: 0.7rem;
        `;
        nasaToggle.addEventListener('click', () => this.toggleNASAData());
        controls.appendChild(nasaToggle);
      }
    }

    // Add parameter selector
    const filterPanel = document.getElementById('filterContent');
    if (filterPanel) {
      const paramSelect = document.createElement('div');
      paramSelect.style.cssText = 'margin-bottom: 10px';
      paramSelect.innerHTML = `
        <label style="font-family:var(--mono);font-size:.65rem;color:var(--t3);display:block;margin-bottom:4px">
          NASA Parameter
        </label>
        <select id="nasaParameterSelect" style="width:100%;background:var(--bg3);border:1px solid var(--border);
          color:var(--t2);font-family:var(--mono);font-size:.7rem;padding:6px 10px;border-radius:4px">
          <option value="chlorophyll">Chlorophyll-a</option>
          <option value="turbidity">Turbidity (Kd490)</option>
          <option value="cdom">CDOM</option>
        </select>
      `;
      filterPanel.appendChild(paramSelect);

      const select = document.getElementById('nasaParameterSelect');
      if (select) {
        select.addEventListener('change', (e) => {
          this.currentParameter = e.target.value;
          this.loadAnalysis();
        });
      }
    }
  }

  async loadAnalysis() {
    try {
      const date = this.currentDate || new Date().toISOString().split('T')[0];
      const response = await app.fetch(
        `/api/nasa/river-analysis?date=${date}&parameter=${this.currentParameter}`
      );

      if (response.success && response.data) {
        this.dataPoints = response.data.data_points;
        this.displayDataPoints(response.data);
        console.log('[NASA] Loaded', this.dataPoints.length, 'river body data points');
      }
    } catch (error) {
      console.error('[NASA] Failed to load analysis:', error);
    }
  }

  displayDataPoints(data) {
    // Remove existing NASA markers if any
    if (window.nasaMarkers) {
      window.nasaMarkers.forEach(marker => window.mapModule?.markerGroup?.removeLayer(marker));
    }
    window.nasaMarkers = [];

    const map = window.mapModule?.map;
    if (!map) return;

    // Add data points as colored circles
    this.dataPoints.forEach(point => {
      const color = this.getColorForStatus(point.status);
      const marker = L.circleMarker([point.lat, point.lng], {
        radius: 8,
        fillColor: color,
        color: '#fff',
        weight: 2,
        opacity: 0.9,
        fillOpacity: 0.7
      }).bindPopup(`
        <div style="font-family: var(--mono); font-size: 0.7rem;">
          <strong>${point.name}</strong><br>
          River: ${point.river}<br>
          State: ${point.state}<br>
          ${this.currentParameter}: ${point.value} ${point.unit}<br>
          Status: ${point.status}<br>
          Date: ${point.date}<br>
          <em>Source: NASA Satellite</em>
        </div>
      `);

      marker.addTo(window.mapModule.markerGroup);
      window.nasaMarkers.push(marker);
    });

    // Update station count
    const countEl = document.getElementById('stationCount');
    if (countEl) {
      countEl.textContent = `${this.dataPoints.length} NASA data points`;
    }
  }

  getColorForStatus(status) {
    switch(status) {
      case 'Good': return '#16A34A';
      case 'Moderate': return '#D97706';
      case 'Poor': return '#DC2626';
      default: return '#6B645C';
    }
  }

  async loadHeatmap() {
    try {
      const date = this.currentDate || new Date().toISOString().split('T')[0];
      const response = await app.fetch(
        `/api/nasa/heatmap-data?date=${date}&parameter=${this.currentParameter}&resolution=50`
      );

      if (response.success && response.data) {
        this.displayHeatmap(response.data);
      }
    } catch (error) {
      console.error('[NASA] Failed to load heatmap:', error);
    }
  }

  displayHeatmap(data) {
    const map = window.mapModule?.map;
    if (!map) return;

    // Remove existing heatmap
    if (this.heatmapLayer) {
      map.removeLayer(this.heatmapLayer);
    }

    // Create heatmap using colored rectangles
    const bounds = data.bbox;
    const gridData = data.grid_data;

    const heatmapGroup = L.layerGroup();

    gridData.forEach(point => {
      const color = this.getColorForStatus(point.status);
      const rect = L.rectangle([
        [point.lat - 0.1, point.lng - 0.1],
        [point.lat + 0.1, point.lng + 0.1]
      ], {
        color: color,
        fillColor: color,
        fillOpacity: 0.3,
        weight: 0
      });

      rect.bindPopup(`
        <div style="font-family: var(--mono); font-size: 0.7rem;">
          ${this.currentParameter}: ${point.value}<br>
          Status: ${point.status}<br>
          Lat: ${point.lat}, Lng: ${point.lng}
        </div>
      `);

      heatmapGroup.addLayer(rect);
    });

    this.heatmapLayer = heatmapGroup;
    heatmapGroup.addTo(map);
  }

  toggleNASAData() {
    const toggle = document.getElementById('nasaToggle');
    if (!toggle) return;

    if (toggle.textContent.includes('Active')) {
      // Deactivate NASA data
      toggle.textContent = '🛰️ NASA Satellite Data';
      toggle.style.background = 'var(--sap)';
      if (window.nasaMarkers) {
        window.nasaMarkers.forEach(marker => window.mapModule?.markerGroup?.removeLayer(marker));
      }
      if (this.heatmapLayer) {
        window.mapModule?.map?.removeLayer(this.heatmapLayer);
      }
    } else {
      // Activate NASA data
      toggle.textContent = '🛰️ NASA Satellite Data (Active)';
      toggle.style.background = '#16A34A';
      this.loadAnalysis();
    }
  }

  setDate(date) {
    this.currentDate = date;
    this.loadAnalysis();
  }
}
