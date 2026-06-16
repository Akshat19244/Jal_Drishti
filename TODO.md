# JalDrishti — Status

## ✅ All issues resolved

### Backend
- [x] CSV path resolution — works from any CWD (config.py)
- [x] CORS — allows all origins for local dev (app.py)
- [x] stations.py `NameError` — pandas import moved to top
- [x] report_generator.py — Categorical fillna TypeError fixed (_safe_df helper)
- [x] report_generator.py — JSON generation works for all 3 formats
- [x] All 16 API methods tested and passing

### Frontend
- [x] All JS files: /api prefix auto-prepended via app.fetch() in main.js
- [x] alerts.js: severity string/number mismatch fixed
- [x] alerts.js: missing threshold_breach field constructed from value/threshold/unit
- [x] beaches.js: response structure fixed (data.beaches not data)
- [x] map.js: dark tiles, NaN basin handled, All-India + basin filter wired
- [x] explorer.js: accordion fixed, NaN basin filtered, pagination works
- [x] dashboard.js: Chart.js dark theme defaults set
- [x] live.js: SSE URL fixed to /api/live/stream
- [x] timeline.js: 400ms debounce added
- [x] index.html: allIndiaBtn, basinFilter, lastUpdated, beachesSummary added

## To run
```
cd backend && python app.py
# open http://localhost:5000/
```
