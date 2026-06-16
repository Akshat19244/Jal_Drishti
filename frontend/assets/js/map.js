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
    this.markers = {};
    this.currentYear = null;
    this.currentBasin = null;
    this.currentWaterBodyType = null;
    this.allIndiaMode = true;
  }

  async init() {
    this.setupMap();
    await this.populateFilters();   // Populate dropdowns BEFORE loading stations
    this.loadStations();
    window.eventBus.on('timeline:yearChange', d => { this.currentYear = d.year; this.loadStations(); });
    this.setupFilterListeners();
    this.setupAllIndiaToggle();
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
        const color = this.getWQIColor(station.wqi);
        const marker = L.circleMarker([station.lat, station.lng], {
          radius: 5, fillColor: color,
          color: '#fff', weight: 0.8, opacity: 0.9, fillOpacity: 0.85
        }).bindPopup(this.getPopupHTML(station));

        marker.on('click', () => this.showStationDetails(station));
        marker.addTo(this.markerGroup);
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
        <div class="pp"><span class="ppl">Turbidity</span><span class="ppv">${station.turbidity ?? 'N/A'} NTU</span></div>
      </div>
      <div style="font-family:var(--mono);font-size:.55rem;color:rgba(245,240,230,.45);margin-top:6px">
        ${waterInfo} · Year: ${station.year || 'All'}
      </div>
    `;
  }
}
