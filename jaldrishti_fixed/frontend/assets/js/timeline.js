/* JalDrishti Timeline Module — Year Slider */

class TimelineModule {
  constructor() {
    this.minYear = 1963;
    this.maxYear = 2025;           // FIX: hardcoded to 2025 (latest with data), not new Date().getFullYear()
    this.currentYear = null;       // FIX: null = "All Years", don't filter on init
    this.init();
  }

  init() {
    this.setupSlider();
    this.loadCoverageData();
  }

  setupSlider() {
    const slider = document.getElementById('yearSlider');
    if (!slider) return;

    slider.min = this.minYear;
    slider.max = this.maxYear;
    slider.value = this.maxYear;  // visually at 2025 but we don't fire event on init

    // Show "All Years" initially — user must drag to pick a year
    this.updateDisplay();

    slider.addEventListener('input', (e) => {
      this.currentYear = parseInt(e.target.value);
      this.updateDisplay();
      clearTimeout(this._debounce);
      this._debounce = setTimeout(() => {
        window.eventBus.emit('timeline:yearChange', { year: this.currentYear });
      }, 400);
    });

    // Double-click to reset to "All Years"
    slider.addEventListener('dblclick', () => {
      this.currentYear = null;
      slider.value = this.maxYear;
      this.updateDisplay();
      window.eventBus.emit('timeline:yearChange', { year: null });
    });
  }

  updateDisplay() {
    const display = document.querySelector('.timeline-year');
    if (display) display.textContent = this.currentYear ? this.currentYear : 'All Years';

    const slider = document.getElementById('yearSlider');
    if (!slider) return;
    const val = this.currentYear || this.maxYear;
    const pct = ((val - this.minYear) / (this.maxYear - this.minYear)) * 100;
    slider.style.backgroundImage = `linear-gradient(to right,
      var(--sap) 0%, var(--sap) ${pct}%,
      var(--bg3) ${pct}%, var(--bg3) 100%)`;
  }

  async loadCoverageData() {
    try {
      const response = await app.fetch('/api/timeline/coverage');
      if (response.coverage) this.renderCoverageBars(response.coverage);
    } catch (error) {
      console.error('[Timeline] Coverage load failed:', error);
    }
  }

  renderCoverageBars(coverage) {
    const container = document.querySelector('.timeline-coverage');
    if (!container) return;
    container.innerHTML = '';
    const maxCount = Math.max(...Object.values(coverage).map(v => parseInt(v) || 0), 1);
    const totalYears = this.maxYear - this.minYear + 1;

    for (let i = 0; i < totalYears; i++) {
      const year = this.minYear + i;
      const count = coverage[String(year)] || 0;
      const pct = count / maxCount;

      const bar = document.createElement('div');
      bar.style.cssText = `flex:1;background:var(--sap);min-height:4px;
        height:${Math.max(pct * 100, 5)}%;
        opacity:${Math.max(pct * 0.9, 0.06)};
        border-radius:1px;cursor:pointer;transition:opacity .15s`;
      bar.title = `${year}: ${count} stations`;
      bar.addEventListener('click', () => {
        const slider = document.getElementById('yearSlider');
        if (slider) { slider.value = year; slider.dispatchEvent(new Event('input')); }
      });
      container.appendChild(bar);
    }
  }
}
