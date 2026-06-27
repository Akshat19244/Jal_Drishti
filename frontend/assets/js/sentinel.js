/* JalDrishti Sentinel-2 Module */

class SentinelModule {
  constructor() {
    this.currentDate = null;
    this.chart = null;
    this.init();
  }

  async init() {
    await this.loadSentinelData();
    this.setupEventListeners();
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
      console.error('[Sentinel] Failed to load data:', e);
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
    // Add a small indicator showing data source
    const existingIndicator = document.getElementById('sentinelDataSource');
    if (existingIndicator) {
      existingIndicator.remove();
    }

    const section = document.getElementById('sentinel');
    if (section) {
      const indicator = document.createElement('div');
      indicator.id = 'sentinelDataSource';
      indicator.style.cssText = 'font-family:var(--mono);font-size:.65rem;color:var(--t3);margin-top:1rem;padding:8px;background:var(--bg3);border-radius:4px;';
      indicator.innerHTML = `
        <strong>Data Source:</strong> ${source === 'sentinel_hub' ? 'Live Sentinel-2 (Copernicus)' : 'Synthetic (CPCB correlations)'} · 
        <strong>Date:</strong> ${this.currentDate || 'Latest'}
      `;
      section.querySelector('div[style*="padding: 0 3rem"]').appendChild(indicator);
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
    }
  }
}
