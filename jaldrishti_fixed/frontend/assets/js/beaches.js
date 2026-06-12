/* JalDrishti Beaches Module — Beach cards + PathoWatch Heatmap */

class BeachesModule {
  constructor() {
    this.heatmapMap = null;
    this.heatLayer = null;
    this.heatMarkers = [];
    this.currentYear = 'all';
  }

  async init() {
    this.loadBeaches();
    this.initHeatmap();
  }

  async loadBeaches() {
    try {
      const response = await app.fetch('/api/beaches');
      const beachData = response.data;
      const beaches = beachData?.beaches || [];
      this.renderBeachCards(beaches);
      this.renderSummary(beachData?.summary || {});
    } catch (error) {
      console.error('[Beaches] Failed to load beaches:', error);
      const scroller = document.querySelector('.beach-scroller');
      if (scroller) scroller.innerHTML = `<div style="color:var(--t3);font-family:var(--mono);font-size:.75rem;padding:1rem;">⚠ Could not load beach data.</div>`;
    }
  }

  renderBeachCards(beaches) {
    const scroller = document.querySelector('.beach-scroller');
    if (!scroller || !beaches.length) return;
    scroller.innerHTML = beaches.map(beach => {
      const rating = beach.bathing_quality || this.getBathingRating(beach.fcol);
      const ratingColor = this.getRatingColor(rating);
      const wqiColor = this.getWQIColor(beach.wqi);
      const fcol = beach.fcol != null ? parseFloat(beach.fcol).toFixed(0) : 'N/A';
      return `
        <div class="beach-card">
          <div style="background:linear-gradient(135deg,rgba(34,85,204,.15),rgba(42,157,143,.1));
            padding:.9rem 1rem .6rem;border-bottom:1px solid var(--border)">
            <div style="font-weight:600;font-size:.88rem;margin-bottom:.2rem">${beach.name}</div>
            <div style="font-family:var(--mono);font-size:.58rem;color:var(--t3)">${beach.state}${beach.district ? ' · '+beach.district : ''}</div>
          </div>
          <div style="padding:.9rem 1rem">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.6rem">
              <span style="font-family:var(--mono);font-size:.62rem;font-weight:600;color:${ratingColor};
                background:${ratingColor}22;padding:2px 8px;border-radius:3px;border:1px solid ${ratingColor}44">
                ${rating}
              </span>
              <span style="font-family:var(--mono);font-size:1.1rem;font-weight:500;color:${wqiColor}">
                ${beach.wqi != null ? beach.wqi : '-'}
              </span>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px">
              <div style="font-family:var(--mono);font-size:.58rem;color:var(--t3)">DO: <span style="color:var(--t2)">${beach.do ?? 'N/A'}</span></div>
              <div style="font-family:var(--mono);font-size:.58rem;color:var(--t3)">BOD: <span style="color:var(--t2)">${beach.bod ?? 'N/A'}</span></div>
              <div style="font-family:var(--mono);font-size:.58rem;color:var(--t3)">pH: <span style="color:var(--t2)">${beach.ph ?? 'N/A'}</span></div>
              <div style="font-family:var(--mono);font-size:.58rem;color:var(--t3)">FColi: <span style="color:${ratingColor}">${fcol}</span></div>
            </div>
          </div>
        </div>`;
    }).join('');
  }

  renderSummary(summary) {
    const el = document.getElementById('beachesSummary');
    if (!el || !Object.keys(summary).length) return;
    const colors = { Excellent:'#16A34A', Good:'#65A30D', Poor:'#D97706', Dangerous:'#DC2626', Unknown:'#6B645C' };
    el.innerHTML = Object.entries(summary).map(([k,v]) =>
      `<span style="font-family:var(--mono);font-size:.62rem;color:${colors[k]||'var(--t2)'};
        background:${colors[k]||'var(--t2)'}22;padding:3px 10px;border-radius:3px;
        border:1px solid ${colors[k]||'var(--t2)'}44">${k}: ${v}</span>`
    ).join('');
  }

  // ── PathoWatch-style heatmap ──────────────────────────────────
  initHeatmap() {
    const container = document.getElementById('beachHeatmapMap');
    if (!container || typeof L === 'undefined') return;

    this.heatmapMap = L.map('beachHeatmapMap', { zoomControl: true }).setView([15.0, 78.0], 5);

    // Tile chain with 3 fallbacks
    const tileChain = [
      ['https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {attribution:'© CartoDB', maxZoom:19, subdomains:'abcd'}],
      ['https://tiles.stadiamaps.com/tiles/alidade_smooth_dark/{z}/{x}/{y}{r}.png', {attribution:'© Stadia', maxZoom:20}],
      ['https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {attribution:'© OSM'}],
    ];
    const tryTile = (idx) => {
      if (idx >= tileChain.length) return;
      const layer = L.tileLayer(tileChain[idx][0], tileChain[idx][1]);
      layer.addTo(this.heatmapMap);
      layer.on('tileerror', () => { this.heatmapMap.removeLayer(layer); tryTile(idx+1); });
    };
    tryTile(0);
    // Force Leaflet to recalculate size once visible (fixes blank map on first render)
    setTimeout(() => { if (this.heatmapMap) this.heatmapMap.invalidateSize(); }, 300);
    setTimeout(() => { if (this.heatmapMap) this.heatmapMap.invalidateSize(); }, 1000);

    // Year selector
    const yearSel = document.getElementById('heatmapYear');
    if (yearSel) {
      const years = ['all',2025,2024,2023,2022,2021,2020,2019,2018];
      yearSel.innerHTML = years.map(y => `<option value="${y}"${y==='all'?' selected':''}>${y === 'all' ? 'All Years' : y}</option>`).join('');
      yearSel.addEventListener('change', () => { this.currentYear = parseInt(yearSel.value); this.loadHeatmap(); });
    }

    this.loadHeatmap();
  }

  async loadHeatmap() {
    const container = document.getElementById('beachHeatmapMap');
    if (!container || !this.heatmapMap) return;

    // Clear existing markers
    this.heatMarkers.forEach(m => this.heatmapMap.removeLayer(m));
    this.heatMarkers = [];

    const legend = document.getElementById('heatmapLegend');
    if (legend) legend.innerHTML = `<span style="font-family:var(--mono);font-size:.62rem;color:var(--t3)">Loading...</span>`;

    try {
      const yearQ = (this.currentYear && this.currentYear !== 'all') ? `?year=${this.currentYear}` : '';
      const response = await app.fetch(`/api/beaches/heatmap${yearQ}`);
      if (!response.success) return;
      const { points, summary } = response.data;

      points.forEach(pt => {
        const radius = Math.max(8, Math.min(30, Math.log10(pt.fcol + 1) * 8));
        const opacity = Math.min(0.9, Math.max(0.3, pt.fcol / 2000));

        const circle = L.circleMarker([pt.lat, pt.lng], {
          radius: radius,
          fillColor: pt.color,
          color: pt.color,
          weight: 1,
          opacity: opacity,
          fillOpacity: opacity * 0.7
        }).bindPopup(`
          <div style="font-family:monospace;font-size:.75rem;min-width:180px">
            <div style="font-weight:700;margin-bottom:4px">${pt.station}</div>
            <div style="color:#888;margin-bottom:6px">${pt.state}</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:3px">
              <span>FColi:</span><span style="color:${pt.color};font-weight:600">${pt.fcol} MPN/100mL</span>
              <span>Status:</span><span style="color:${pt.color};font-weight:600;text-transform:capitalize">${pt.safety}</span>
              ${pt.do != null ? `<span>DO:</span><span>${pt.do} mg/L</span>` : ''}
              ${pt.bod != null ? `<span>BOD:</span><span>${pt.bod} mg/L</span>` : ''}
              ${pt.ph != null ? `<span>pH:</span><span>${pt.ph}</span>` : ''}
            </div>
            <div style="margin-top:6px;padding-top:4px;border-top:1px solid #333;font-size:.65rem;color:#666">
              CPCB Bathing Standard: FColi ≤ 500 MPN/100mL
            </div>
          </div>
        `);
        circle.addTo(this.heatmapMap);
        this.heatMarkers.push(circle);
      });

      // Update legend
      if (legend) {
        legend.innerHTML = `
          <div style="font-family:var(--mono);font-size:.62rem;display:flex;gap:1rem;flex-wrap:wrap;align-items:center">
            <span style="color:#16A34A">● Safe to Swim (FColi &lt; 100)</span>
            <span style="color:#EAB308">● Suspicious (100–500)</span>
            <span style="color:#DC2626">● Contaminated (&gt; 500)</span>
            <span style="color:var(--t3);margin-left:auto">
              Safe: ${summary.safe} · Suspicious: ${summary.suspicious} · Contaminated: ${summary.contaminated}
            </span>
          </div>`;
      }
    } catch (e) {
      console.error('[Beaches] Heatmap load failed:', e);
    }
  }

  getBathingRating(fcol) {
    if (fcol == null) return 'Unknown';
    if (fcol < 100)  return 'Excellent';
    if (fcol < 500)  return 'Good';
    if (fcol < 1000) return 'Poor';
    return 'Dangerous';
  }
  getRatingColor(r) {
    return {Excellent:'#16A34A',Good:'#65A30D',Poor:'#D97706',Dangerous:'#DC2626',Unknown:'#6B645C'}[r]||'#6B645C';
  }
  getWQIColor(wqi) {
    if (!wqi) return '#6B645C';
    if (wqi<=25) return '#16A34A'; if (wqi<=50) return '#65A30D';
    if (wqi<=75) return '#D97706'; if (wqi<=90) return '#EA580C';
    return '#DC2626';
  }
}
