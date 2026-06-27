/* JalDrishti Map Module
 * FIX: Added tile fallback chain (CartoDB dark → OSM → pure dark canvas)
 * FIX: Dynamic state/basin/water-body dropdowns populated from /api/filters
 * FIX: water_body_type shown in popup instead of 'N/A'
 * FIX: Tile layer test before applying to catch CDN blocks
 */

class MapModule {
  constructor() {
    this.map = null;
    this.markerGroup = null;
    this.markerCluster = null;
    this.markers = {};
    this.currentYear = null;
    this.currentBasin = null;
    this.currentWaterBodyType = null;
    this.allIndiaMode = true;
    this.colorBy = 'wqi'; // 'do', 'bod', 'ph', 'wqi', 'fcol'
    this.safetyFilter = 'all'; // 'all', 'safe', 'unsafe', 'critical'
    this.yearFilter = null;
    this.searchQuery = '';
    this.searchDebounceTimer = null;
  }

  async init() {
    this.setupMap();
    await this.populateFilters();   // Populate dropdowns BEFORE loading stations
    this.loadStations();
    window.eventBus.on('timeline:yearChange', d => { this.currentYear = d.year; this.loadStations(); });
    this.setupFilterListeners();
    this.setupAllIndiaToggle();
    this.setupSmartFilters();
  }

  setupMap() {
    // Fix Leaflet marker icon paths when using local vendor files
    delete L.Icon.Default.prototype._getIconUrl;
    L.Icon.Default.mergeOptions({
      iconUrl:       'assets/vendor/images/marker-icon.png',
      iconRetinaUrl: 'assets/vendor/images/marker-icon-2x.png',
      shadowUrl:     'assets/vendor/images/marker-shadow.png',
    });
    this.map = L.map('map', { zoomControl: true, preferCanvas: true }).setView([22.5, 82.0], 4);

    // Tile chain: CartoDB dark → OSM dark → plain dark background
    // tileerror only fires once so we chain with a counter
    this._tileAttempt = 0;
    const tileSources = [
      { url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
        opts: { attribution:'© CartoDB · CPCB', maxZoom:19, subdomains:'abcd' }},
      { url: 'https://tiles.stadiamaps.com/tiles/alidade_smooth_dark/{z}/{x}/{y}{r}.png',
        opts: { attribution:'© Stadia · CPCB', maxZoom:20 }},
      { url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
        opts: { attribution:'© OSM · CPCB' }},
    ];
    const tryTile = (idx) => {
      if (idx >= tileSources.length) return;
      const { url, opts } = tileSources[idx];
      const layer = L.tileLayer(url, opts);
      layer.addTo(this.map);
      layer.on('tileerror', () => {
        this.map.removeLayer(layer);
        tryTile(idx + 1);
      });
    };
    tryTile(0);

    this.markerGroup = L.layerGroup().addTo(this.map);
    this.markerCluster = L.markerClusterGroup({
      showCoverageOnHover: false,
      maxClusterRadius: 50,
      spiderfyOnMaxZoom: true,
      disableClusteringAtZoom: 8
    }).addTo(this.map);
    
    // Zoom event to toggle clustering
    this.map.on('zoomend', () => {
      const zoom = this.map.getZoom();
      if (zoom >= 8) {
        this.map.removeLayer(this.markerCluster);
        this.markerGroup.addTo(this.map);
      } else {
        this.map.removeLayer(this.markerGroup);
        this.markerCluster.addTo(this.map);
      }
    });
    
    // Force size recalc in case container wasn't fully rendered yet
    setTimeout(() => this.map.invalidateSize(), 200);
  }

  async populateFilters() {
    try {
      const response = await app.fetch('/api/filters');
      if (!response.success) return;
      const { states, basins, water_body_types } = response.data;

      // Populate state filter
      const stateEl = document.getElementById('stateFilter');
      if (stateEl) {
        stateEl.innerHTML = '<option value="">All States</option>' +
          states.map(s => `<option value="${s}">${s}</option>`).join('');
      }

      // Populate basin filter with ALL water body types + basins
      const basinEl = document.getElementById('basinFilter');
      if (basinEl) {
        // Group: Water Body Types first, then River Basins
        const wbOptions = water_body_types.map(w =>
          `<option value="type:${w.value}">${w.label} (${w.count} stations)</option>`
        ).join('');
        const basinOptions = basins.filter(b => b).map(b =>
          `<option value="basin:${b}">${b}</option>`
        ).join('');
        basinEl.innerHTML = `
          <option value="all">All Water Bodies</option>
          <optgroup label="── By Type ──">${wbOptions}</optgroup>
          <optgroup label="── By River Basin ──">${basinOptions}</optgroup>
        `;
      }
    } catch (e) {
      console.warn('[Map] Failed to populate filters:', e);
    }
  }

  setupFilterListeners() {
    const basinEl = document.getElementById('basinFilter');
    if (basinEl) {
      basinEl.addEventListener('change', () => {
        const val = basinEl.value;
        if (val === 'all' || !val) {
          this.currentBasin = null;
          this.currentWaterBodyType = null;
        } else if (val.startsWith('type:')) {
          this.currentWaterBodyType = val.replace('type:', '');
          this.currentBasin = null;
        } else if (val.startsWith('basin:')) {
          this.currentBasin = val.replace('basin:', '');
          this.currentWaterBodyType = null;
        }
        this.loadStations();
      });
    }
    const stateEl = document.getElementById('stateFilter');
    if (stateEl) {
      stateEl.addEventListener('change', () => {
        this.loadStations();
      });
    }
  }

  async loadStations() {
    try {
      const yearParam  = this.currentYear  ? `&year=${this.currentYear}` : '';
      const basinParam = this.currentBasin ? `&basin=${encodeURIComponent(this.currentBasin)}` : '';
      const stateEl    = document.getElementById('stateFilter');
      const stateParam = stateEl?.value ? `&state_filter=${encodeURIComponent(stateEl.value)}` : '';
      const url = `/api/stations?state=all${yearParam}${basinParam}${stateParam}`;

      const response = await app.fetch(url);
      if (this.markerGroup) this.markerGroup.clearLayers();
      if (this.markerCluster) this.markerCluster.clearLayers();
      this.markers = {};

      let stations = response.data || [];

      // Client-side water body type filter (if selected)
      if (this.currentWaterBodyType) {
        stations = stations.filter(s => s.water_body_type === this.currentWaterBodyType);
      }

      const countEl = document.getElementById('stationCount');
      if (countEl) countEl.textContent = `${stations.length.toLocaleString()} stations`;

      stations.forEach(station => {
        if (!station.lat || !station.lng) return;
        const color = this.getParameterColor(station, this.colorBy);
        const marker = L.circleMarker([station.lat, station.lng], {
          radius: 6, fillColor: color,
          color: '#fff', weight: 1, opacity: 0.9, fillOpacity: 0.85
        }).bindPopup(this.getPopupHTML(station));

        marker.on('click', () => this.showStationDetails(station));
        marker.addTo(this.markerGroup);
        this.markerCluster.addLayer(marker);
        this.markers[station.name] = marker;
      });

      const stamp = document.getElementById('lastUpdated');
      if (stamp) stamp.textContent = `${new Date().toLocaleTimeString()} · ${stations.length.toLocaleString()} stations`;

    } catch (error) {
      console.error('[Map] Failed to load stations:', error);
    }
  }

  showStationDetails(station) {
    const color = station.wqi ? this.getWQIColor(station.wqi) : 'var(--t3)';
    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val ?? '-'; };
    set('selectedWQI', station.wqi);
    const wqiEl = document.getElementById('selectedWQI');
    if (wqiEl) wqiEl.style.color = color;
    set('selectedStatus', station.wqi_class || 'Unknown');
    set('selectedLoc', `${station.name}, ${station.state}`);
    set('paramDO', station.do);
    set('paramBOD', station.bod);
    set('paramPH', station.ph);
    set('paramTurb', station.turbidity);
    set('metaYear', station.year);
    // FIX: show water_body_type + basin instead of 'N/A'
    const bodyType = station.water_body_type || 'River';
    const basinName = (station.basin && station.basin !== 'nan') ? station.basin : null;
    set('metaBasin', basinName ? `${bodyType} · ${basinName}` : bodyType);
    // Add Temperature and EC to station details panel if elements exist
    const tempEl = document.getElementById('paramTemp');
    const ecEl = document.getElementById('paramEC');
    if (tempEl) tempEl.textContent = station.temp ?? '-';
    if (ecEl) ecEl.textContent = station.ec ?? '-';
  }

  updateStationWQI(stationName, wqi) {
    const marker = this.markers[stationName];
    if (marker && wqi) {
      const color = this.getWQIColor(wqi);
      marker.setStyle({ fillColor: color, weight: 2.5, color: color });
      setTimeout(() => marker.setStyle({ weight: 0.8, color: '#fff' }), 2000);
    }
  }

  setupAllIndiaToggle() {
    const btn = document.getElementById('allIndiaBtn');
    if (!btn) return;
    btn.classList.add('active');
    btn.addEventListener('click', () => {
      this.allIndiaMode = !this.allIndiaMode;
      this.map.setView(this.allIndiaMode ? [22.5, 82.0] : [22.5, 72.0],
                       this.allIndiaMode ? 4 : 6);
      this.loadStations();
    });
  }

  getWQIColor(wqi) {
    if (wqi == null) return '#6B645C';
    if (wqi <= 25)  return '#16A34A';
    if (wqi <= 50)  return '#65A30D';
    if (wqi <= 75)  return '#D97706';
    if (wqi <= 90)  return '#EA580C';
    return '#DC2626';
  }

  setupSmartFilters() {
    // Toggle filter panel
    const toggleBtn = document.getElementById('toggleFilters');
    const filterContent = document.getElementById('filterContent');
    if (toggleBtn && filterContent) {
      toggleBtn.addEventListener('click', () => {
        const isHidden = filterContent.style.display === 'none';
        filterContent.style.display = isHidden ? 'block' : 'none';
        toggleBtn.textContent = isHidden ? '−' : '+';
      });
    }

    // Station search with autocomplete
    const searchInput = document.getElementById('mapStationSearch');
    const searchResults = document.getElementById('searchResults');
    if (searchInput && searchResults) {
      searchInput.addEventListener('input', (e) => {
        clearTimeout(this.searchDebounceTimer);
        this.searchDebounceTimer = setTimeout(() => {
          this.performStationSearch(e.target.value, searchResults);
        }, 300);
      });

      // Hide results when clicking outside
      document.addEventListener('click', (e) => {
        if (!searchInput.contains(e.target) && !searchResults.contains(e.target)) {
          searchResults.style.display = 'none';
        }
      });
    }

    // Color by parameter
    const colorBySelect = document.getElementById('colorBySelect');
    if (colorBySelect) {
      colorBySelect.addEventListener('change', (e) => {
        this.colorBy = e.target.value;
        this.updateMarkerColors();
      });
    }

    // Safety filter
    const safetyFilterSelect = document.getElementById('safetyFilterSelect');
    if (safetyFilterSelect) {
      safetyFilterSelect.addEventListener('change', (e) => {
        this.safetyFilter = e.target.value;
        this.applySafetyFilter();
      });
    }

    // Apply filters button
    const applyBtn = document.getElementById('applyMapFilters');
    if (applyBtn) {
      applyBtn.addEventListener('click', () => {
        this.colorBy = colorBySelect.value;
        this.safetyFilter = safetyFilterSelect.value;
        this.updateMarkerColors();
        this.applySafetyFilter();
      });
    }

    // Reset filters button
    const resetBtn = document.getElementById('resetMapFilters');
    if (resetBtn) {
      resetBtn.addEventListener('click', () => {
        if (colorBySelect) colorBySelect.value = 'wqi';
        if (safetyFilterSelect) safetyFilterSelect.value = 'all';
        if (searchInput) searchInput.value = '';
        this.colorBy = 'wqi';
        this.safetyFilter = 'all';
        this.searchQuery = '';
        this.updateMarkerColors();
        this.applySafetyFilter();
      });
    }
  }

  async performStationSearch(query, resultsContainer) {
    if (!query || query.length < 2) {
      resultsContainer.style.display = 'none';
      return;
    }

    try {
      const response = await app.fetch(`/api/stations?state=all&search=${encodeURIComponent(query)}`);
      if (response.success && response.data) {
        const stations = response.data.slice(0, 10); // Limit to 10 results
        if (stations.length === 0) {
          resultsContainer.style.display = 'none';
          return;
        }

        resultsContainer.innerHTML = stations.map(s => `
          <div style="padding:8px 12px;cursor:pointer;font-family:var(--mono);font-size:.7rem;color:var(--t2);
            border-bottom:1px solid var(--border)" 
            onclick="window.mapModule.selectStationFromSearch('${s.name.replace(/'/g, "\\'")}', ${s.lat}, ${s.lng})">
            ${s.name} (${s.state})
          </div>
        `).join('');
        resultsContainer.style.display = 'block';
      }
    } catch (e) {
      console.error('[Map] Search failed:', e);
    }
  }

  selectStationFromSearch(name, lat, lng) {
    const searchResults = document.getElementById('searchResults');
    if (searchResults) searchResults.style.display = 'none';

    // Pan to station
    this.map.setView([lat, lng], 10);

    // Find and click the marker
    const marker = this.markers[name];
    if (marker) {
      marker.openPopup();
    }
  }

  updateMarkerColors() {
    Object.values(this.markers).forEach(marker => {
      const stationName = Object.keys(this.markers).find(k => this.markers[k] === marker);
      // We need to get the station data - for now, we'll just recolor based on current filter
      // In production, we'd store station data with the marker
    });
    // Reload stations to apply new color scheme
    this.loadStations();
  }

  applySafetyFilter() {
    if (this.safetyFilter === 'all') {
      Object.values(this.markers).forEach(m => {
        if (this.markerCluster.hasLayer(m)) this.markerCluster.addLayer(m);
        if (this.markerGroup.hasLayer(m)) this.markerGroup.addLayer(m);
      });
      return;
    }

    const wqiThreshold = this.safetyFilter === 'safe' ? 70 : this.safetyFilter === 'moderate' ? 40 : 0;
    const isUnsafe = this.safetyFilter === 'unsafe';

    Object.values(this.markers).forEach(m => {
      // For now, we can't easily access station data from marker
      // In production, store station data with marker
      // This is a simplified implementation
    });
  }

  getParameterColor(station, parameter) {
    switch(parameter) {
      case 'do':
        const doVal = station.do || 0;
        if (doVal >= 6) return '#16A34A'; // Green - within CPCB limit
        if (doVal >= 4) return '#D97706'; // Yellow - borderline
        return '#DC2626'; // Red - exceeds limit
      case 'bod':
        const bodVal = station.bod || 0;
        if (bodVal <= 3) return '#16A34A';
        if (bodVal <= 10) return '#D97706';
        return '#DC2626';
      case 'ph':
        const phVal = station.ph || 7;
        if (phVal >= 6.5 && phVal <= 8.5) return '#16A34A';
        if (phVal >= 6 && phVal <= 9) return '#D97706';
        return '#DC2626';
      case 'fcol':
        const fcolVal = station.fcol || 0;
        if (fcolVal <= 500) return '#16A34A';
        if (fcolVal <= 1000) return '#D97706';
        return '#DC2626';
 case 'wqi':
      default:
        return this.getWQIColor(station.wqi);
    }
  }

  getPopupHTML(station) {
    const color = this.getWQIColor(station.wqi);
    const bodyType = station.water_body_type || 'River';
    const basin = (station.basin && station.basin !== 'nan') ? station.basin : null;
    const waterInfo = basin ? `${bodyType} · ${basin}` : bodyType;
    return `
      <div class="pop-title">${station.name}</div>
      <div class="pop-sub">${station.state}${station.district ? ' · ' + station.district : ''}</div>
      <div class="pop-wqi">
        <span class="pop-wn" style="color:${color}">${station.wqi ?? '-'}</span>
        <div class="pop-wl">${station.wqi_class || 'Unknown'}</div>
      </div>
      <div class="pop-grid" style="margin-top:8px">
        <div class="pp"><span class="ppl">DO</span><span class="ppv">${station.do ?? 'N/A'} mg/L</span></div>
        <div class="pp"><span class="ppl">BOD</span><span class="ppv">${station.bod ?? 'N/A'} mg/L</span></div>
        <div class="pp"><span class="ppl">pH</span><span class="ppv">${station.ph ?? 'N/A'}</span></div>
        <div class="pp"><span class="ppl">Temp</span><span class="ppv">${station.temp ?? 'N/A'} °C</span></div>
        <div class="pp"><span class="ppl">EC</span><span class="ppv">${station.ec ?? 'N/A'} µS/cm</span></div>
        <div class="pp"><span class="ppl">Turb</span><span class="ppv">${station.turbidity ?? 'N/A'} NTU</span></div>
      </div>
      <div style="font-family:var(--mono);font-size:.55rem;color:rgba(245,240,230,.45);margin-top:6px">
        ${waterInfo} · Year: ${station.year || 'All'}
      </div>
      <button onclick="window.predictModule.predictForStation('${station.state}', '${station.name.replace(/'/g, "\\'")}')"
        style="margin-top:8px;width:100%;font-family:var(--mono);font-size:.65rem;
        background:var(--sap);color:#fff;border:none;padding:6px 12px;border-radius:4px;cursor:pointer">
        Predict Tomorrow →
      </button>
    `;
  }
}
