# 🌾 The Harvest Squeeze
### *Quantifying the 'Growing vs. Moving' Cost Crisis in US Soybeans (2026)*

A professional Ag-Tech analytics platform that classifies US agricultural counties by profitability risk. Combines USDA yield forecasts, FRED fertilizer indices, EIA diesel prices, NASA SMAP soil moisture, and MODIS NDVI to compute a county-level **Net Margin Score** — then maps the entire soybean value chain spatially.

---

## 🏗️ Project Architecture

```
harvest_squeeze/
├── config.py              # All constants: costs, risk thresholds, API config
├── data_acquisition.py    # API fetch functions (USDA, FRED, EIA, GEE)
├── data_processing.py     # KD-Tree spatial analysis + cost model
├── app.py                 # Streamlit dashboard (Pydeck map + Plotly charts)
├── requirements.txt       # Python dependencies
├── .env.example           # API key template
└── USSoyValueChain.xlsx   # EIA/NOPA facility spatial data (place here)
```

### Data Flow

```
USSoyValueChain.xlsx ──────────────────────────────────┐
                                                        ▼
USDA QuickStats ──► County Yields ──►  KD-Tree     County Risk
FRED API ─────────► Fertilizer PPI ──► Spatial   ──► Score  ──► Streamlit
EIA API ──────────► Diesel Price  ──►  Analysis      (NMS)      Dashboard
GEE (optional) ───► NDVI / SMAP ──►  Cost Model              (Pydeck + Plotly)
Census TIGER ─────► County Centroids ──────────────────┘
```

---

## 🚀 Quick Start

### 1. Clone & Install

```bash
git clone <your-repo>
cd harvest_squeeze
pip install -r requirements.txt
```

### 2. Place the XLSX

Copy `USSoyValueChain.xlsx` into the project root (same folder as `app.py`).

### 3. Set API Keys

```bash
cp .env.example .env
# Edit .env with your three free API keys
```

| API | Free Registration | Data |
|-----|-------------------|------|
| [USDA NASS QuickStats](https://quickstats.nass.usda.gov/api) | ✅ Instant | County yields, planted acres |
| [FRED](https://fred.stlouisfed.org/docs/api/api_key.html) | ✅ Instant | Nitrogenous Fertilizer PPI |
| [EIA](https://www.eia.gov/opendata/register.php) | ✅ Instant | Weekly US Diesel Price |

### 4. Run the Dashboard

```bash
streamlit run app.py
```

### 5. (Optional) Authenticate GEE

```python
import ee
ee.Authenticate()    # One-time browser auth
ee.Initialize()
```

Then enable **"Use GEE Satellite Data"** in the sidebar to pull live MODIS NDVI and NASA SMAP soil moisture.

---

## 📊 Model Components

### Growing It: Bio-Chemical Component

**Production Cost Stack ($/acre, 2026 baseline):**

| Cost Item | $/acre | Source |
|-----------|--------|--------|
| Land Rent | $248 | USDA NASS 2024 Cash Rent |
| Fertilizer (base) | $45 | USDA ERS + FRED PPI adj. |
| Seed | $62 | USDA ERS 2024 + inflation |
| Pesticides | $38 | USDA ERS |
| Fuel/Labor/Other | ~$67 | USDA ERS + EIA diesel adj. |
| **Total** | **~$460** | |

**NDVI Yield Adjustment:**
```
adj_yield = base_yield × (1 + 0.12 × ndvi_z_score)
```

### Moving It: Logistics Component

**Transport Cost Model ($/bushel):**
```
base_cost = (miles_to_crusher / 100) × $0.18/100mi
diesel_adj = 1 + 0.65 × (live_diesel - $3.82) / $3.82
penalty = 1.25 if distance > 75 miles else 1.0
transport_cost = base_cost × diesel_adj × penalty
```

**KD-Tree Performance:**
- 3,100 counties × 67 crushers: nearest-neighbor search in ~2ms
- Uses Haversine chord approximation for angular distance

### Net Margin Score (NMS)

```
NMS = (Revenue - Total Costs - Transport Basis) / Revenue
```

| Risk Tier | NMS | Color |
|-----------|-----|-------|
| 🔴 HIGH | ≤ 0% (loss) | Red |
| 🟠 ELEVATED | 0–5% | Orange |
| 🟡 MODERATE | 5–12% | Yellow |
| 🟢 HEALTHY | > 12% | Green |

---

## 🛠️ Development Notes

### Running Tests

```bash
# Test data acquisition (requires API keys)
python data_acquisition.py

# Test processing engine (no API keys needed)
python data_processing.py
```

### Adding a New State

Change the `Pilot State` dropdown in the sidebar or modify the `state_filter` parameter in `build_profitability_model()`.

### Extending to National View

The model handles all CONUS counties. Remove `state_filter` in `build_profitability_model()` to run nationally (~3,100 counties). County centroids are cached in `data/cache/county_centroids.parquet` after first download.

### GEE Integration Notes

The `fetch_gee_ndvi_by_county()` function samples MODIS MOD13A2 (1km, 16-day composite) using a 15km buffer around county centroids during the June–August peak growing season. Sampling 99 Iowa counties takes ~3-5 minutes on GEE standard tier.

---

## 📚 Data Sources

| Source | Data | Update Frequency |
|--------|------|-----------------|
| USDA NASS QuickStats | County-level yield (bu/acre), planted acres | Annual (December) |
| FRED `PCU3253113253111` | Nitrogenous Fertilizer PPI | Monthly |
| EIA `EMD_EPD2D_PTE_NUS_DPG` | US No.2 Diesel Retail Price | Weekly |
| EIA/NOPA (XLSX) | Soybean processor + export terminal locations | Annual |
| NASA MODIS MOD13A2 (GEE) | NDVI 1km growing-season mean | 16-day composite |
| NASA SMAP (GEE) | Root-zone soil moisture 10km | ~3-day |
| Census TIGER 2023 | County boundaries & centroids | Annual |

---

## 🌐 Deployment (Streamlit Cloud)

1. Push to GitHub (ensure `.env` is in `.gitignore`)
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Add secrets in the Streamlit Cloud dashboard under **Settings → Secrets**:
   ```toml
   USDA_API_KEY = "your_key"
   FRED_API_KEY = "your_key"
   EIA_API_KEY = "your_key"
   ```
4. Deploy — live URL suitable for portfolio/resume

---

*Built with Python 3.11+ | Streamlit | Pydeck | Plotly | GeoPandas | SciPy KDTree*
