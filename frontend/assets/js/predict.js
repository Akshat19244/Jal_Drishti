/* JalDrishti Dual-Model Water Quality Classification System */

class PredictModule {
  constructor() {
    this.riverBodies = [];
    this.parameters = ['DO', 'BOD', 'pH', 'FC', 'EC', 'Nitrate', 'Turbidity'];
    this.init();
  }

  async init() {
    await this.loadRiverBodies();
    this.setupEventListeners();
  }

  async loadRiverBodies() {
    try {
      const response = await app.fetch('/api/predict-condition/river-bodies');
      if (response.success && response.data) {
        this.riverBodies = response.data.river_bodies;
        this.populateRiverBodyDropdown();
      }
    } catch (e) {
      console.error('[Predict] Failed to load river bodies:', e);
    }
  }

  populateRiverBodyDropdown() {
    const riverSelect = document.getElementById('riverBodySelect');
    if (riverSelect) {
      riverSelect.innerHTML = '<option value="">Select River Body</option>' +
        this.riverBodies.map(r => `<option value="${r}">${r}</option>`).join('');
    }
  }

  populateParameterDropdown() {
    const paramSelect = document.getElementById('parameterSelect');
    if (paramSelect) {
      paramSelect.innerHTML = '<option value="">Select Parameter</option>' +
        this.parameters.map(p => `<option value="${p}">${p}</option>`).join('');
    }
  }

  setupEventListeners() {
    const checkBtn = document.getElementById('checkConditionBtn');
    if (checkBtn) {
      checkBtn.addEventListener('click', () => this.runConditionCheck());
    }
  }

  async runConditionCheck() {
    const riverBody = document.getElementById('riverBodySelect').value;
    const parameter = document.getElementById('parameterSelect').value;

    if (!riverBody || !parameter) {
      alert('Please select River Body and Parameter');
      return;
    }

    const btn = document.getElementById('checkConditionBtn');
    btn.disabled = true;
    btn.textContent = 'Analyzing...';

    try {
      const response = await app.fetch('/api/predict-condition/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ river_body: riverBody, parameter: parameter })
      });

      if (response.success && response.data) {
        this.displayResults(response.data);
      } else {
        alert('Analysis failed: ' + (response.error || 'Unknown error'));
      }
    } catch (e) {
      console.error('[Predict] Analysis failed:', e);
      alert('Analysis failed. Please try again.');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Check Water Body Condition';
    }
  }

  displayResults(data) {
    // Update Model A card
    this.updateModelCard('modelACard', data.model_a);

    // Update Model B card
    this.updateModelCard('modelBCard', data.model_b);

    // Update Combined Verdict card
    this.updateCombinedVerdictCard(data);

    // Update explanation panel
    this.updateExplanation(data.explanation);

    // Show results section
    const resultsSection = document.getElementById('predictResults');
    if (resultsSection) resultsSection.style.display = 'block';
  }

  updateModelCard(cardId, modelData) {
    const card = document.getElementById(cardId);
    if (!card) return;

    const classBadge = card.querySelector('.class-badge');
    const confidenceBar = card.querySelector('.confidence-bar');
    const confidenceValue = card.querySelector('.confidence-value');
    const sourceText = card.querySelector('.source-text');

    if (classBadge) {
      classBadge.textContent = modelData.class;
      classBadge.className = 'class-badge ' + this.getClassColor(modelData.class);
    }

    if (confidenceBar) {
      const confidence = modelData.confidence * 100;
      confidenceBar.style.width = `${confidence}%`;
      confidenceBar.style.backgroundColor = this.getClassColor(modelData.class);
    }

    if (confidenceValue) {
      confidenceValue.textContent = `${(modelData.confidence * 100).toFixed(1)}%`;
    }

    if (sourceText) {
      sourceText.textContent = modelData.source;
      if (modelData.data_source === 'proxy') {
        sourceText.innerHTML += ' <span style="font-size:0.6rem;color:var(--t3)">(proxy data)</span>';
      }
    }
  }

  updateCombinedVerdictCard(data) {
    const card = document.getElementById('combinedVerdictCard');
    if (!card) return;

    const verdictBadge = card.querySelector('.verdict-badge');
    const agreementIndicator = card.querySelector('.agreement-indicator');
    const combinedConfidence = card.querySelector('.combined-confidence');

    if (verdictBadge) {
      verdictBadge.textContent = data.combined_verdict;
      verdictBadge.className = 'verdict-badge ' + this.getClassColor(data.combined_verdict);
    }

    if (agreementIndicator) {
      agreementIndicator.textContent = data.agreement_message;
      if (data.agreement === 'high') {
        agreementIndicator.style.color = '#16A34A';
      } else if (data.agreement === 'moderate') {
        agreementIndicator.style.color = '#D97706';
      } else {
        agreementIndicator.style.color = '#DC2626';
      }
    }

    if (combinedConfidence) {
      combinedConfidence.textContent = `Confidence: ${(data.combined_confidence * 100).toFixed(1)}%`;
    }
  }

  updateExplanation(explanation) {
    const explanationPanel = document.getElementById('explanationPanel');
    if (explanationPanel) {
      explanationPanel.textContent = explanation;
    }
  }

  getClassColor(className) {
    switch(className.toLowerCase()) {
      case 'safe': return 'status-safe';
      case 'moderate': return 'status-moderate';
      case 'unsafe': return 'status-unsafe';
      default: return '';
    }
  }

  // Called from map popup
  checkConditionForRiver(riverBody) {
    // Navigate to predict section
    document.getElementById('predict-sec').scrollIntoView({ behavior: 'smooth' });

    // Pre-fill dropdown
    const riverSelect = document.getElementById('riverBodySelect');
    if (riverSelect) {
      riverSelect.value = riverBody;
    }
  }
}
