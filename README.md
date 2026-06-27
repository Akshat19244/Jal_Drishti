# JalDrishti — Water Quality Intelligence Platform
**ISRO SAC · SRTD/RTMG/MISA Division · Ahmedabad**

Satellite-powered water quality monitoring for Indian water bodies. Fuses Sentinel-2 imagery with CPCB/CWC ground-truth data across 370,000+ records spanning 34 states (1963–2025).

**New Features (v2.0):**
- **ML Water Quality Predictor**: AI-powered forecasting using RandomForestRegressor with 7-day predictions
- **Enhanced Explorer**: Sorting, smart filtering, search highlighting, inline expand with sparklines
- **WQI Methodology Panel**: Interactive dashboard panel explaining WQI calculation
- **Sentinel-2 Advanced Indices**: Live satellite data integration (CDOM, Turbidity, Chlorophyll-a, Kd490) with Copernicus Sentinel Hub API support
- **Map Enhancements**: Smart filtering, station search, dynamic marker colors, marker clustering
- **Additional Parameters**: Temperature and Electrical Conductivity (EC) display throughout

---

## Quick Start (3 steps)

```bash
# 1. Install dependencies (run from project root)
cd backend
pip install -r requirements.txt

# 2. Start the backend
python app.py

# 3. Open the frontend
# Visit: http://localhost:5000/
# OR open frontend/index.html directly in a browser
```

---

## Project Structure

```
jal drishti/
├── .env                          ← your config (LLM key, CSV path)
├── india_research_full.csv       ← 370K-row dataset (stays here)
│
├── backend/
│   ├── app.py                    ← Flask entry point: python app.py
│   ├── config.py                 ← env config, resolves CSV path automatically
│   ├── requirements.txt
│   ├── reports/                  ← generated PDF/CSV/JSON reports land here
│   │
│   ├── routes/
│   │   ├── timeline.py           ← GET /api/timeline
│   │   ├── stations.py           ← GET /api/stations, /api/stations/namo-gangu
│   │   ├── explorer.py           ← GET /api/explorer/state|station|river
│   │   ├── alerts.py             ← GET /api/alerts
│   │   ├── report.py             ← POST /api/report/generate
│   │   ├── chat.py               ← POST /api/chat
│   │   ├── beaches.py            ← GET /api/beaches
│   │   ├── live.py               ← GET /api/live/stream (SSE)
│   │   └── predict.py            ← POST /api/predict (ML forecasting)
│   │
│   └── services/
│       ├── data_service.py       ← CSV loading, pandas queries, singleton cache
│       ├── wqi_calculator.py     ← WQI formula + CPCB thresholds
│       ├── llm_service.py        ← Anthropic/OpenAI/Gemini chatbot wrapper
│       ├── report_generator.py  ← PDF (reportlab) + CSV + JSON export
│       └── ml_service.py         ← RandomForestRegressor model for predictions
│
└── frontend/
    ├── index.html
    └── assets/
        ├── css/
        │   ├── main.css          ← core layout + design system
        │   ├── theme.css         ← light/dark CSS variables
        │   └── components.css    ← cards, map, chatbot, modals
        └── js/
            ├── main.js           ← app init, theme toggle, API wrapper
            ├── map.js            ← Leaflet map, markers, smart filters, clustering
            ├── dashboard.js      ← Chart.js charts (WQI, trend, state comparison)
            ├── timeline.js       ← year slider + coverage histogram
            ├── explorer.js       ← state/station/river tabs with sorting/filtering
            ├── predict.js        ← ML Water Quality Predictor module
            ├── alerts.js         ← smart alerts + timeline
            ├── chatbot.js        ← JalBot AI assistant
            ├── report.js         ← PDF/CSV/JSON export modal
            ├── beaches.js        ← coastal water quality cards
            └── live.js           ← SSE real-time feed listener
```

---

## Configuration (.env)

```env
# LLM for JalBot chatbot (optional — falls back to rule-based if empty)
LLM_PROVIDER=anthropic          # openai | anthropic | gemini
LLM_API_KEY=                    # your key here

# Sentinel-2 Satellite Data (optional — falls back to synthetic data if empty)
# Get API key from: https://www.sentinel-hub.com/
SENTINEL_HUB_API_KEY=

# Data
CSV_PATH=india_research_full.csv  # relative to project root

# Server
PORT=5000
DEBUG=true
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Backend status + row count |
| GET | `/api/timeline?year=2020&state=Gujarat` | Station data for year |
| GET | `/api/timeline/coverage` | Station count per year (histogram) |
| GET | `/api/timeline/trend` | National WQI trend over years |
| GET | `/api/stations?state=all&basin=Ganga&year=2024` | Station list with WQI |
| GET | `/api/stations/namo-gangu` | Ganga basin summary |
| GET | `/api/explorer/state` | State-wise WQI choropleth data |
| GET | `/api/explorer/station?page=1&limit=50` | Paginated station table |
| GET | `/api/explorer/river` | Basin accordion data |
| GET | `/api/alerts?state=Gujarat&year=2024` | Smart alerts by threshold |
| GET | `/api/beaches` | Coastal water quality + bathing rating |
| POST | `/api/predict` | ML water quality prediction (RandomForestRegressor) |
| GET | `/api/sentinel/indices?date=YYYY-MM-DD` | Sentinel-2 water quality indices (CDOM, Turbidity, Chlorophyll-a, Kd490) |
| GET | `/api/sentinel/historical?start_date=&end_date=` | Historical Sentinel-2 indices |
| GET | `/api/sentinel/status` | Sentinel-2 service status and configuration |
| POST | `/api/chat` | JalBot AI chatbot |
| POST | `/api/report/generate` | Generate PDF/CSV/JSON report |
| GET | `/api/report/download/:id` | Download generated report |
| GET | `/api/live/stream` | SSE real-time station updates |

---

## Bugs Fixed

| # | File | Bug | Fix |
|---|------|-----|-----|
| 1 | All JS files | API calls missing `/api` prefix (e.g. `/stations` → 404) | `main.js` auto-prepends `/api` to all `app.fetch()` calls |
| 2 | `config.py` | `CSV_PATH` resolved from CWD → crashes if launched from wrong directory | Now resolved from project root (`__file__` based) |
| 3 | `app.py` | CORS blocked `file://` and non-standard ports | Changed to `origins: "*"` for dev |
| 4 | `alerts.js` | Read `alert.severity` as a number (it's a string `"Critical"/"Warning"`) | Fixed severity class logic |
| 5 | `alerts.js` | Referenced `alert.threshold_breach` (field doesn't exist in backend) | Constructed display string from `value`/`threshold`/`unit` |
| 6 | `beaches.js` | Tried to re-derive `bathing_quality` — backend already returns it | Uses `beach.bathing_quality` directly |
| 7 | `beaches.js` | Response shape was `data.beaches` not `data` | Destructured `response.data.beaches` |
| 8 | `stations.py` | `import pandas as pd` was at bottom of file → `NameError` in `/search` | Moved import to top |
| 9 | `report_generator.py` | `fillna('')` on Categorical DataFrame columns → `TypeError` in pandas 2.x | `_safe_df()` converts categoricals to str first |
| 10 | `map.js` | Hardcoded light map tiles, `nan` basin shown in popup | Dark CartoDB tiles, `nan` → `'N/A'` |
| 11 | `explorer.js` | Accordion click handler re-attached on every render, `nan` basin in table | Single toggle logic, basin `nan` filtered |
| 12 | `dashboard.js` | Chart.js color defaults never set → pale unreadable labels | `setupChartDefaults()` sets dark-theme colors |
| 13 | `live.js` | SSE URL was `/live/stream` (missing `/api`) | Fixed to `/api/live/stream` |
| 14 | `timeline.js` | No debounce on slider — fired API call on every pixel drag | 400ms debounce on `input` event |
| 15 | `index.html` | Missing `id="allIndiaBtn"`, `id="basinFilter"`, `id="lastUpdated"`, `id="beachesSummary"` | All four elements added |

---

## Data Schema

`india_research_full.csv` — 370,463 rows × 28 columns

Key columns: `pH`, `DO`, `BOD`, `COD`, `EC`, `Total_Coliform`, `Fecal_Coliform`, `Nitrate`, `TDS`, `Turbidity`, `Safety` (Safe/Unsafe), `State`, `District`, `Basin`, `Station_Name`, `Date`, `Year`, `Latitude`, `Longitude`

---

*Built for ISRO SAC · SRTD/RTMG/MISA · Intern: Akshat · Mentor: Dr. Surisetty V V Arun Kumar*
