/* JalDrishti Alerts Module — Alert Cards & Timeline */

class AlertsModule {
  constructor() { this.init(); }

  init() { this.loadAlerts(); }

  async loadAlerts() {
    const grid = document.getElementById('alertsGrid');
    if (grid) grid.innerHTML = `<div style="color:var(--t3);font-family:var(--mono);font-size:.75rem;padding:1rem;">Loading alerts...</div>`;
    try {
      // FIX: was '/alerts?limit=9', now correctly '/api/alerts?limit=9'
      const response = await app.fetch('/api/alerts?state=Gujarat&limit=9');
      this.renderAlertCards(response.data?.alerts || []);
      this.loadAlertTimeline();
    } catch (error) {
      console.error('[Alerts] Failed to load alerts:', error);
      if (grid) grid.innerHTML = `<div style="color:var(--crit);font-family:var(--mono);font-size:.75rem;padding:1rem;">⚠ Could not load alerts. Is the backend running?</div>`;
    }
  }

  renderAlertCards(alerts) {
    const container = document.getElementById('alertsGrid');
    if (!container) return;
    if (!alerts.length) {
      container.innerHTML = `<div style="color:var(--t3);font-family:var(--mono);font-size:.75rem;grid-column:1/-1;padding:1rem">No threshold breaches found for selected filters.</div>`;
      return;
    }

    container.innerHTML = alerts.slice(0, 9).map(alert => {
      // FIX: backend returns severity as 'Critical'/'Warning'/'Info' string, not a number
      const sev = alert.severity || 'Info';
      const sevClass = sev === 'Critical' ? 'cr' : sev === 'Warning' ? 'wn' : 'in';
      const sevLabel = sev === 'Critical' ? '● Critical Alert' : sev === 'Warning' ? '◆ Warning' : '◉ Advisory';
      const score = alert.severity_score || 0;

      // FIX: backend has no 'threshold_breach' field — construct it from value/threshold/unit
      const thresholdTag = `${alert.parameter}: ${alert.value} ${alert.unit || ''}`.trim();

      // Format date and time
      const dateTime = alert.date ? new Date(alert.date).toLocaleString('en-IN', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      }) : 'N/A';

      return `
        <div class="ac ${sevClass}">
          <div style="display:flex;justify-content:space-between;align-items:flex-start">
            <div class="asev">${sevLabel}</div>
            <div style="font-family:var(--mono);font-size:.58rem;background:rgba(245,240,230,.06);
              border:1px solid var(--border);padding:2px 7px;border-radius:3px;color:var(--t3)">
              Score: ${score}
            </div>
          </div>
          <div class="atitle">${alert.station} — ${alert.parameter}</div>
          <div class="adesc">${alert.message}</div>
          <div class="ameta">
            <span>${alert.state}${alert.district ? ' · ' + alert.district : ''}</span>
            <span class="atag">${thresholdTag}</span>
          </div>
          <div style="margin-top:8px;font-family:var(--mono);font-size:.6rem;color:var(--t3)">
            📅 ${dateTime}
          </div>
        </div>
      `;
    }).join('');
  }

  async loadAlertTimeline() {
    try {
      // FIX: backend endpoint is /api/alerts/timeline, not /api/alerts/timeline?days=30
      const response = await app.fetch('/api/alerts/timeline?state=Gujarat&parameter=BOD');
      this.renderTimeline(response.data?.timeline || []);
    } catch (error) {
      console.error('[Alerts] Failed to load timeline:', error);
    }
  }

  renderTimeline(events) {
    const container = document.querySelector('.alert-timeline .timeline-vertical');
    if (!container) return;
    if (!events.length) {
      container.innerHTML = `<div style="color:var(--t3);font-size:.75rem;padding:.5rem">No historical data available.</div>`;
      return;
    }
    container.innerHTML = events.map(event => {
      // Format date
      const dateStr = event.date ? new Date(event.date).toLocaleDateString('en-IN', {
        day: '2-digit',
        month: 'short',
        year: 'numeric'
      }) : 'N/A';

      return `
        <div class="timeline-item">
          <div class="timeline-date">${dateStr}</div>
          <div class="timeline-event">
            <div style="font-weight:600;color:var(--t1)">${event.station || 'Unknown Station'}</div>
            <div style="font-size:.7rem;color:var(--t3);margin-top:2px">
              ${event.water_body_type || 'River'} ${event.basin ? '· ' + event.basin : ''}
            </div>
            <div style="margin-top:4px">
              ${event.count} readings · Avg: <b>${event.avg}</b> ${event.unit || 'mg/L'} (Max: ${event.max})
            </div>
          </div>
        </div>
      `;
    }).join('');
  }
}
