/* JalDrishti Beach Water Quality Classification System */
/* ML-powered swimming suitability prediction with human-readable insights */

class PredictModule {
  constructor() {
    this.stations = [];
    this.init();
  }

  async init() {
    await this.loadStations();
    this.setupEventListeners();
  }

  async loadStations() {
    try {
      const response = await app.fetch('/api/beach-predict/stations');
      if (response.success && response.data) {
        this.stations = response.data;
        this.populateStationDropdown();
      }
    } catch (e) {
      console.error('[BeachPredict] Failed to load stations:', e);
    }
  }

  populateStationDropdown() {
    const select = document.getElementById('beachStationSelect');
    if (!select) return;
    select.innerHTML = '<option value="">Select a beach...</option>' +
      this.stations.map(s => `<option value="${s.name}">${s.name} (${s.state})</option>`).join('');
  }

  setupEventListeners() {
    const btn = document.getElementById('classifyBeachBtn');
    if (btn) {
      btn.addEventListener('click', () => this.runClassification());
    }
  }

  async runClassification() {
    const station = document.getElementById('beachStationSelect').value;
    if (!station) {
      this.showToast('Please select a beach station to classify');
      return;
    }

    const btn = document.getElementById('classifyBeachBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="btn-spinner"></span> Analyzing...';

    try {
      const response = await app.fetch('/api/beach-predict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ station })
      });

      if (response.success && response.data) {
        this.displayResults(response.data);
      } else {
        this.showToast(response.error || 'Analysis failed');
      }
    } catch (e) {
      console.error('[BeachPredict] Error:', e);
      this.showToast('Analysis failed. Please try again.');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Classify Water Quality';
    }
  }

  displayResults(data) {
    const results = document.getElementById('beachPredictResults');
    if (!results) return;
    results.style.display = 'block';

    this.updateScoreRing(data);
    this.updateTopContributors(data);
    this.updateParameterTable(data);
    this.updateInterpretation(data);
    this.updateModelInfo(data);

    results.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  updateScoreRing(data) {
    const score = data.swimming_suitability_score;
    const label = data.suitability_label;
    const color = data.suitability_color;

    const ring = document.getElementById('suitabilityRing');
    const text = document.getElementById('suitabilityText');
    const labelEl = document.getElementById('suitabilityLabel');
    const classEl = document.getElementById('suitabilityClass');

    if (ring) {
      ring.style.background = `conic-gradient(${color} ${score}%, var(--bg3) ${score}%)`;
    }
    if (text) text.textContent = score;
    if (labelEl) {
      labelEl.textContent = label;
      labelEl.style.color = color;
    }
    if (classEl) {
      const badge = classEl;
      badge.textContent = data.classification;
      badge.className = 'pred-badge ' + (data.classification === 'Safe' ? 'status-safe' : 'status-unsafe');
    }
  }

  updateTopContributors(data) {
    const container = document.getElementById('topContributors');
    if (!container || !data.top_contributors) return;

    container.innerHTML = data.top_contributors.map((c, i) => {
      const isBad = c.status === 'high' || c.status === 'low';
      const icon = isBad ? '⚠️' : '✓';
      const color = isBad ? 'var(--crit)' : 'var(--ok)';
      return `
        <div class="contributor-item">
          <div class="contributor-rank">#${i + 1}</div>
          <div class="contributor-body">
            <div class="contributor-header">
              <span style="color: ${color}; font-weight: 600;">${icon} ${c.label}</span>
              <span class="contributor-value">${c.value} ${c.unit}</span>
            </div>
            <div class="contributor-bar-wrap">
              <div class="contributor-bar" style="width: ${Math.min(Math.abs(c.impact_score) * 100, 100)}%; background: ${color};"></div>
            </div>
            <div class="contributor-desc">${isBad ? 'Exceeds safe limits' : 'Within safe limits'}</div>
          </div>
        </div>
      `;
    }).join('');
  }

  updateParameterTable(data) {
    const container = document.getElementById('parameterBreakdown');
    if (!container || !data.parameter_breakdown) return;

    const rows = data.parameter_breakdown.map(p => {
      let statusClass = 'status-safe';
      let statusText = '✓ Safe';
      if (p.status === 'high') { statusClass = 'status-unsafe'; statusText = '⚠ High'; }
      else if (p.status === 'low') { statusClass = 'status-warn'; statusText = '↓ Low'; }
      return `
        <tr>
          <td style="padding: 8px 10px; color: var(--t1); font-size: .75rem;">
            <div style="font-weight: 500;">${p.label}</div>
            ${p.explanation ? `<div style="font-size: .6rem; color: var(--t3); margin-top: 2px; max-width: 200px;">${p.explanation}</div>` : ''}
          </td>
          <td style="padding: 8px 10px; font-family: var(--mono); font-size: .75rem; color: var(--t2);">${p.value} ${p.unit}</td>
          <td style="padding: 8px 10px;"><span class="pred-badge ${statusClass}" style="font-size: .6rem; padding: 2px 8px;">${statusText}</span></td>
          <td style="padding: 8px 10px;"><div class="impact-bar-wrap"><div class="impact-bar" style="width: ${Math.min(Math.abs(p.impact_score) * 100, 100)}%; background: ${p.status === 'high' || p.status === 'low' ? 'var(--crit)' : 'var(--ok)'};"></div></div></td>
        </tr>
      `;
    }).join('');

    container.innerHTML = `
      <table style="width: 100%; border-collapse: collapse;">
        <thead>
          <tr style="border-bottom: 1px solid var(--border);">
            <th style="padding: 10px; text-align: left; font-size: .65rem; color: var(--t3); text-transform: uppercase; letter-spacing: .05em;">Parameter</th>
            <th style="padding: 10px; text-align: left; font-size: .65rem; color: var(--t3); text-transform: uppercase; letter-spacing: .05em;">Value</th>
            <th style="padding: 10px; text-align: left; font-size: .65rem; color: var(--t3); text-transform: uppercase; letter-spacing: .05em;">Status</th>
            <th style="padding: 10px; text-align: left; font-size: .65rem; color: var(--t3); text-transform: uppercase; letter-spacing: .05em;">Impact</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    `;
  }

  updateInterpretation(data) {
    const container = document.getElementById('beachInterpretation');
    if (!container) return;
    const text = data.interpretation || 'Analysis complete.';
    const isSafe = data.classification === 'Safe';
    container.innerHTML = text.replace(/\n/g, '<br>');
    container.style.borderLeftColor = isSafe ? 'var(--ok)' : 'var(--crit)';
  }

  updateModelInfo(data) {
    const container = document.getElementById('beachModelInfo');
    if (!container) return;
    container.innerHTML = `
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: .75rem;">
        <div class="model-stat">
          <span class="model-stat-label">Station</span>
          <span class="model-stat-value">${data.station_name}</span>
        </div>
        <div class="model-stat">
          <span class="model-stat-label">State</span>
          <span class="model-stat-value">${data.station_summary.state}</span>
        </div>
        <div class="model-stat">
          <span class="model-stat-label">Data Span</span>
          <span class="model-stat-value">${data.station_summary.year_range}</span>
        </div>
        <div class="model-stat">
          <span class="model-stat-label">Model</span>
          <span class="model-stat-value">RandomForest (300 trees)</span>
        </div>
      </div>
    `;
  }

  showToast(msg) {
    const existing = document.querySelector('.beach-toast');
    if (existing) existing.remove();
    const toast = document.createElement('div');
    toast.className = 'beach-toast';
    toast.textContent = msg;
    document.body.appendChild(toast);
    setTimeout(() => toast.classList.add('show'), 10);
    setTimeout(() => { toast.classList.remove('show'); setTimeout(() => toast.remove(), 300); }, 3000);
  }
}
