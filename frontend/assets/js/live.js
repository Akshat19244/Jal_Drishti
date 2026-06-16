/* JalDrishti Live Module — Server-Sent Events Stream */

class LiveModule {
  constructor() {
    this.eventSource = null;
    this.isConnected = false;
    this.lastUpdateTime = null;
    this.tickInterval = null;
    this.init();
  }

  init() {
    // Delay SSE connection slightly so app is fully initialized
    setTimeout(() => this.connectStream(), 2000);
    window.addEventListener('beforeunload', () => this.disconnect());
  }

  connectStream() {
    try {
      // FIX: was '/live/stream' → needs full /api path
      const url = `${window.app.API}/api/live/stream`;
      this.eventSource = new EventSource(url);

      this.eventSource.addEventListener('update', (e) => {
        try {
          const data = JSON.parse(e.data);
          this.handleUpdate(data);
          this.lastUpdateTime = new Date();
          this.updateLiveIndicator(true);
          this.startTick();
        } catch (err) {
          console.warn('[Live] Parse error:', err);
        }
      });

      this.eventSource.addEventListener('error', () => {
        this.updateLiveIndicator(false);
        // Silently retry — SSE is optional
        setTimeout(() => this.reconnect(), 10000);
      });

      this.isConnected = true;
    } catch (e) {
      console.warn('[Live] SSE not available:', e);
    }
  }

  handleUpdate(data) {
    // Update map marker color if visible
    if (window.mapModule && window.mapModule.updateStationWQI) {
      window.mapModule.updateStationWQI(data.station_name, data.wqi);
    }
    // Update last updated indicator
    const stamp = document.getElementById('lastUpdated');
    if (stamp) stamp.textContent = `Updated: ${new Date().toLocaleTimeString()}`;
  }

  startTick() {
    if (this.tickInterval) return;
    this.tickInterval = setInterval(() => {
      const stamp = document.getElementById('lastUpdated');
      if (stamp && this.lastUpdateTime) {
        const secs = Math.round((new Date() - this.lastUpdateTime) / 1000);
        stamp.textContent = `Last update: ${secs}s ago`;
      }
    }, 5000);
  }

  updateLiveIndicator(connected) {
    const pill = document.querySelector('.nav-pill');
    const dot = document.querySelector('.live-dot');
    if (pill) pill.style.opacity = connected ? '1' : '0.45';
    if (dot) dot.style.background = connected ? '#4ADE80' : '#6B645C';
  }

  disconnect() {
    if (this.eventSource) { this.eventSource.close(); this.isConnected = false; }
    if (this.tickInterval) { clearInterval(this.tickInterval); this.tickInterval = null; }
  }

  reconnect() { this.disconnect(); this.connectStream(); }
}
