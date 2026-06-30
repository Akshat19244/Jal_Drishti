/* NASA Satellite Analysis Module — River Body Data Points on Sentinel-2 Map */

class NASAAnalysisModule {
  constructor() {
    this.currentDate = null;
    this.currentParameter = 'chlorophyll';
    this.dataPoints = [];
    this.heatmapLayer = null;
    this.init();
  }

  init() {
    // NASA analysis is now integrated into Sentinel-2 section only
    // No auto-load on init
  }

  async loadAnalysis(date, parameter, mapInstance) {
    try {
      this.currentDate = date;
      this.currentParameter = parameter;
      
      const response = await app.fetch(
        `/api/nasa/river-analysis?date=${date}&parameter=${parameter}`
      );

      if (response.success && response.data) {
        this.displayDataPoints(response.data, mapInstance);
        console.log('[NASA] Loaded', response.data.data_points.length, 'river body data points on Sentinel-2 map');
      }
    } catch (error) {
      console.error('[NASA] Failed to load analysis:', error);
    }
  }

  displayDataPoints(data, mapInstance) {
    // Display NASA data points on the provided map (Sentinel-2 map)
    if (!mapInstance) return;

    // Remove existing NASA markers if any
    if (window.nasaMarkers) {
      window.nasaMarkers.forEach(marker => mapInstance.removeLayer(marker));
    }
    window.nasaMarkers = [];

    // Add data points as colored circles
    this.dataPoints = data.data_points || [];
    
    this.dataPoints.forEach(point => {
      const color = this.getColorForStatus(point.status);
      const marker = L.circleMarker([point.lat, point.lng], {
        radius: 6,
        fillColor: color,
        color: '#fff',
        weight: 2,
        opacity: 0.9,
        fillOpacity: 0.7
      }).bindPopup(`
        <div style="font-family: var(--mono); font-size: 0.7rem;">
          <strong>${point.name}</strong><br>
          River: ${point.river}<br>
          State: ${point.state}<br>
          ${this.currentParameter}: ${point.value} ${point.unit}<br>
          Status: ${point.status}<br>
          Date: ${point.date}<br>
          <em>Source: NASA Satellite</em>
        </div>
      `);

      marker.addTo(mapInstance);
      window.nasaMarkers.push(marker);
    });

    console.log('[NASA] Displayed', this.dataPoints.length, 'data points on Sentinel-2 map');
  }

  getColorForStatus(status) {
    switch(status) {
      case 'Good': return '#16A34A';
      case 'Moderate': return '#D97706';
      case 'Poor': return '#DC2626';
      default: return '#6B645C';
    }
  }

  clearMarkers(mapInstance) {
    if (window.nasaMarkers) {
      window.nasaMarkers.forEach(marker => mapInstance.removeLayer(marker));
    }
    window.nasaMarkers = [];
  }
}
