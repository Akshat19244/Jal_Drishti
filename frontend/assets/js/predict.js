/* JalDrishti ML Predictor Module */

class PredictModule {
  constructor() {
    this.states = [];
    this.stations = [];
    this.currentStation = null;
    this.forecastChart = null;
    this.init();
  }

  async init() {
    await this.loadStates();
    this.setupEventListeners();
  }

  async loadStates() {
    try {
      const response = await app.fetch('/api/explorer/state');
      if (response.success && response.data) {
        this.states = response.data.map(s => s.state);
        this.populateStateDropdown();
      }
    } catch (e) {
      console.error('[Predict] Failed to load states:', e);
    }
  }

  populateStateDropdown() {
    const stateSelect = document.getElementById('predictState');
    if (stateSelect) {
      stateSelect.innerHTML = '<option value="">Select State</option>' +
        this.states.map(s => `<option value="${s}">${s}</option>`).join('');
    }
  }

  async loadStations(state) {
    try {
      const response = await app.fetch(`/api/stations?state=${encodeURIComponent(state)}`);
      if (response.success && response.data) {
        this.stations = response.data;
        this.populateStationDropdown();
      }
    } catch (e) {
      console.error('[Predict] Failed to load stations:', e);
    }
  }

  populateStationDropdown() {
    const stationSelect = document.getElementById('predictStation');
    if (stationSelect) {
      stationSelect.innerHTML = '<option value="">Select Station</option>' +
        this.stations.map(s => `<option value="${s.name}">${s.name}</option>`).join('');
    }
  }

  setupEventListeners() {
    const stateSelect = document.getElementById('predictState');
    if (stateSelect) {
      stateSelect.addEventListener('change', (e) => {
        if (e.target.value) {
          this.loadStations(e.target.value);
        }
      });
    }

    const predictBtn = document.getElementById('predictBtn');
    if (predictBtn) {
      predictBtn.addEventListener('click', () => this.runPrediction());
    }
  }

  async runPrediction() {
    const state = document.getElementById('predictState').value;
    const station = document.getElementById('predictStation').value;
    const parameter = document.getElementById('predictParameter').value;

    if (!state || !station || !parameter) {
      alert('Please select State, Station, and Parameter');
      return;
    }

    const btn = document.getElementById('predictBtn');
    btn.disabled = true;
    btn.textContent = 'Predicting...';

    try {
      const response = await app.fetch('/api/predict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ state, station, parameter })
      });

      if (response.success || response.predicted_value !== undefined) {
        this.displayResults(response);
      } else {
        alert('Prediction failed: ' + (response.error || 'Unknown error'));
      }
    } catch (e) {
      console.error('[Predict] Prediction failed:', e);
      alert('Prediction failed. Please try again.');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Predict';
    }
  }

  displayResults(data) {
    this.currentStation = data.station;

    // Update prediction card
    const predValueEl = document.getElementById('predValue');
    const predUnitEl = document.getElementById('predUnit');
    const predStatusEl = document.getElementById('predStatus');
    const predWQIEl = document.getElementById('predWQI');

    if (predValueEl) predValueEl.textContent = data.predicted_value;
    if (predUnitEl) predUnitEl.textContent = data.unit;
    if (predStatusEl) {
      predStatusEl.textContent = data.safety_status;
      predStatusEl.className = 'pred-badge ' + this.getStatusClass(data.safety_status);
    }
    if (predWQIEl) predWQIEl.textContent = `WQI: ${data.wqi}`;

    // Update forecast chart
    this.renderForecastChart(data.seven_day_forecast);

    // Update confusion matrix
    this.renderConfusionMatrix(data.confusion_matrix, data.cm_labels);

    // Update model metrics
    this.renderModelMetrics(data.model_metrics);

    // Show results section
    const resultsSection = document.getElementById('predictResults');
    if (resultsSection) resultsSection.style.display = 'block';
  }

  getStatusClass(status) {
    switch(status.toLowerCase()) {
      case 'safe': return 'status-safe';
      case 'moderate': return 'status-moderate';
      case 'unsafe': return 'status-unsafe';
      default: return '';
    }
  }

  renderForecastChart(forecast) {
    const ctx = document.getElementById('forecastChart');
    if (!ctx) return;

    if (this.forecastChart) {
      this.forecastChart.destroy();
    }

    const labels = ['Tomorrow', 'Day 2', 'Day 3', 'Day 4', 'Day 5', 'Day 6', 'Day 7'];
    const t3 = getComputedStyle(document.documentElement).getPropertyValue('--t3').trim();
    const grid = 'rgba(128,128,128,0.1)';

    this.forecastChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [{
          label: 'Predicted Value',
          data: forecast,
          borderColor: '#2255CC',
          backgroundColor: 'rgba(34,85,204,0.1)',
          fill: true,
          tension: 0.4,
          pointBackgroundColor: '#2255CC',
          pointBorderColor: '#fff',
          pointRadius: 4
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false }
        },
        scales: {
          y: {
            ticks: { color: t3 },
            grid: { color: grid }
          },
          x: {
            ticks: { color: t3 },
            grid: { display: false }
          }
        }
      }
    });
  }

  renderConfusionMatrix(cm, labels) {
    const container = document.getElementById('confusionMatrix');
    if (!container) return;

    let html = '<table class="cm-table">';
    html += '<tr><th></th>';
    labels.forEach(l => html += `<th>Predicted<br>${l}</th>`);
    html += '</tr>';

    for (let i = 0; i < cm.length; i++) {
      html += `<tr><th>Actual<br>${labels[i]}</th>`;
      for (let j = 0; j < cm[i].length; j++) {
        const isDiagonal = i === j;
        const bgColor = isDiagonal ? 'rgba(22,163,74,0.2)' : 'rgba(220,38,38,0.2)';
        const textColor = isDiagonal ? '#16A34A' : '#DC2626';
        html += `<td style="background:${bgColor};color:${textColor};font-weight:bold">${cm[i][j]}</td>`;
      }
      html += '</tr>';
    }
    html += '</table>';

    container.innerHTML = html;
  }

  renderModelMetrics(metrics) {
    const container = document.getElementById('modelMetrics');
    if (!container) return;

    container.innerHTML = `
      <div class="metric-card">
        <div class="metric-label">RMSE</div>
        <div class="metric-value">${metrics.rmse}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">MAE</div>
        <div class="metric-value">${metrics.mae}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">R²</div>
        <div class="metric-value">${metrics.r2}</div>
      </div>
    `;
  }

  // Called from map popup
  predictForStation(state, station) {
    // Navigate to predict section
    document.getElementById('predict-sec').scrollIntoView({ behavior: 'smooth' });

    // Pre-fill dropdowns
    const stateSelect = document.getElementById('predictState');
    const stationSelect = document.getElementById('predictStation');

    if (stateSelect) {
      stateSelect.value = state;
      // Trigger change to load stations
      stateSelect.dispatchEvent(new Event('change'));
    }

    // Wait for stations to load, then select the station
    setTimeout(() => {
      if (stationSelect) {
        stationSelect.value = station;
      }
    }, 500);
  }
}
