# The Harvest Squeeze — Deployment Guide

This document covers every step required to run, test, and deploy the
Harvest Squeeze dashboard in three environments: local development,
Streamlit Community Cloud (public portfolio), and Docker (production/server).

---

## Table of Contents

1. [Local Development Setup](#1-local-development-setup)
2. [First-Run Configuration](#2-first-run-configuration)
3. [API Key Registration](#3-api-key-registration)
4. [Google Earth Engine Authentication](#4-google-earth-engine-authentication)
5. [Running the Dashboard](#5-running-the-dashboard)
6. [Streamlit Community Cloud Deployment](#6-streamlit-community-cloud-deployment)
7. [Docker Deployment](#7-docker-deployment)
8. [Environment Variables Reference](#8-environment-variables-reference)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Local Development Setup

### Prerequisites

- Python 3.11 or higher (3.12 is supported)
- Git
- 2 GB free disk space (Census TIGER download on first run: ~75 MB)
- Internet access to census.gov, api.stlouisfed.org, eia.gov, quickstats.nass.usda.gov

### Step 1 — Clone and navigate

```bash
git clone https://github.com/your-username/harvest-squeeze.git
cd harvest-squeeze
```

### Step 2 — Create a virtual environment

```bash
# macOS and Linux
python3 -m venv .venv
source .venv/bin/activate

# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Always activate this environment before working on the project.
The shell prompt will show `(.venv)` when it is active.

### Step 3 — Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

This installs approximately 1.4 GB of packages including NumPy, SciPy,
GeoPandas, Streamlit, Pydeck, Plotly, and the Google Earth Engine API.

### Step 4 — Place the data file

Copy `USSoyValueChain.xlsx` into the project root (the same folder as `app.py`).
This file is required and cannot be substituted.

### Step 5 — Set API keys

```bash
cp .env.example .env
```

Open `.env` in a text editor and fill in your four free API keys.
See Section 3 for registration links.

---

## 2. First-Run Configuration

### Build the county centroid cache

The spatial model requires county centroids for all 3,108 CONUS counties.
On the first run, the application will attempt to download Census TIGER
shapefiles automatically. If that succeeds, precise INTPTLAT/INTPTLON
coordinates are saved to `data/cache/county_centroids.parquet`.

If your machine cannot reach `www2.census.gov` (firewalled environments,
corporate networks, CI runners), run the offline fallback:

```bash
python build_centroids.py offline
```

This generates approximate centroids (within 25–50 miles) using the bundled
`addfips` FIPS table and state bounding boxes. This accuracy is fully
sufficient for the KD-Tree logistics model, which measures distances of
30–200+ miles.

To upgrade to precise Census centroids later when you have access:

```bash
python build_centroids.py
```

This overwrites the cache with exact coordinates and prints a validation report.

### Verify the data pipeline

Run the processing engine test (no API keys required):

```bash
python data_processing.py
```

You should see output similar to:

```
Iowa counties loaded: 99
KD-Tree query — crusher: median=37 mi, max=107 mi
KD-Tree query — terminal: median=138 mi, max=235 mi
Production model: Mean NMS 14.9% | Tiers: {HEALTHY: 99}
Processing test complete.
```

Run the data acquisition test (requires API keys in `.env`):

```bash
python data_acquisition.py
```

---

## 3. API Key Registration

All four API keys are free and issued instantly.

### USDA NASS QuickStats

URL: https://quickstats.nass.usda.gov/api

1. Navigate to the URL above.
2. Click "Request an API Key."
3. Enter your email address and click Submit.
4. You will receive your key by email within a few minutes.
5. Add it to `.env` as `USDA_API_KEY=your_key_here`.

What it powers: county-level soybean and corn yield estimates,
planted acreage, and crop progress/condition weekly data.

### FRED — St. Louis Federal Reserve

URL: https://fredaccount.stlouisfed.org/apikey

1. Create a free FRED account at https://fredaccount.stlouisfed.org/login/secure/
2. Once logged in, navigate to the API Keys page.
3. Click "Request API Key," enter a reason (e.g., "agricultural research"),
   and submit.
4. The key appears on the same page immediately.
5. Add it to `.env` as `FRED_API_KEY=your_key_here`.

What it powers: Nitrogenous Fertilizer Producer Price Index
(series PCU3253113253111) for fertilizer cost adjustment.

### EIA — Energy Information Administration

URL: https://www.eia.gov/opendata/register.php

1. Navigate to the URL above.
2. Enter your name, organization, and email address, then click Register.
3. Your API key will be emailed to you within a few minutes.
4. Add it to `.env` as `EIA_API_KEY=your_key_here`.

What it powers: weekly US No. 2 Diesel Retail Price
(series EMD_EPD2D_PTE_NUS_DPG) for transport cost adjustment.

---

## 4. Google Earth Engine Authentication

GEE is optional. The model runs fully without it; satellite data adds
a yield modifier of plus or minus 15% based on NDVI and soil moisture.

### Step 1 — Register for GEE access

URL: https://earthengine.google.com/signup/

You need a Google account. Approval is usually instant for non-commercial use.
Select "Unpaid usage" and "Academia or Research" when prompted.

### Step 2 — Install and authenticate

The `earthengine-api` package is already in `requirements.txt`.
Run authentication once from the terminal:

```python
import ee
ee.Authenticate()   # Opens a browser for Google OAuth
ee.Initialize()     # Verifies the credentials work
```

This saves credentials to `~/.config/earthengine/credentials`.
You will not need to authenticate again on the same machine.

### Step 3 — Test the pipeline

```bash
python gee_pipeline.py
```

With a valid authenticated session this will fetch NDVI data for a sample
of Iowa counties and print the results. Without authentication it will
print clear instructions on what to run.

### Step 4 — Use in the dashboard

Navigate to the Satellite View page. Click "Load Demo Data" for synthetic
data or "Fetch Satellite Data" for live GEE observations. For commercial
GEE accounts (cloud projects), enter your GEE Project ID in the sidebar
before fetching.

### Service Account Authentication (CI / Cloud Deployment)

For headless servers where interactive OAuth is not possible:

1. Create a service account in Google Cloud Console.
2. Grant it the "Earth Engine Resource Viewer" role.
3. Download the JSON key file.
4. In the sidebar, enter the service account email and path to the key file
   (or set them as environment variables `GEE_SERVICE_ACCOUNT` and
   `GEE_KEY_FILE`).

---

## 5. Running the Dashboard

### Start the development server

```bash
streamlit run app.py
```

The dashboard opens at http://localhost:8501. All four pages are accessible
from the left navigation sidebar.

### Useful launch flags

```bash
# Custom port
streamlit run app.py --server.port 8080

# Disable file watcher (slightly faster in production)
streamlit run app.py --server.fileWatcherType none

# Headless mode (no browser opens)
streamlit run app.py --server.headless true
```

### Page navigation

The multi-page structure is automatic. Streamlit reads filenames from
`pages/` and displays them in alphanumeric order. The current pages are:

| File                          | Page name             |
|-------------------------------|-----------------------|
| `app.py`                      | Main Risk Map         |
| `pages/1_National_Risk_View.py`  | National Risk View  |
| `pages/2_Crop_Progress.py`    | Crop Progress         |
| `pages/3_Scenario_Analysis.py`| Scenario Analysis     |
| `pages/4_Satellite_View.py`   | Satellite View        |

---

## 6. Streamlit Community Cloud Deployment

Streamlit Community Cloud is free for public repositories and provides
a shareable URL suitable for a portfolio or resume.

### Step 1 — Prepare the repository

Ensure the following files are in your repository root:

```
app.py
config.py
crop_progress.py
data_acquisition.py
data_processing.py
gee_pipeline.py
build_centroids.py
styles.py
requirements.txt
pages/
USSoyValueChain.xlsx     ← must be committed to the repo
data/cache/county_centroids.parquet   ← pre-build and commit this
```

**Important:** Pre-build the county centroid cache locally and commit it.
Streamlit Cloud cannot reach census.gov, so the app will use the offline
fallback unless the parquet file is already present.

```bash
# Build the offline centroid cache
python build_centroids.py offline

# Add to git (parquet files are binary — confirm .gitignore does not exclude them)
git add data/cache/county_centroids.parquet
git commit -m "Add pre-built county centroid cache"
```

Add API keys to `.gitignore` and never commit the `.env` file:

```
# .gitignore entries to verify
.env
__pycache__/
*.pyc
.venv/
```

### Step 2 — Push to GitHub

```bash
git remote add origin https://github.com/your-username/harvest-squeeze.git
git branch -M main
git push -u origin main
```

### Step 3 — Connect to Streamlit Community Cloud

1. Go to https://share.streamlit.io and sign in with GitHub.
2. Click "New app."
3. Select your repository and the branch (`main`).
4. Set the main file path to `app.py`.
5. Click "Advanced settings" and add your secrets (see below).
6. Click "Deploy."

### Step 4 — Add secrets

In the Streamlit Cloud dashboard, navigate to your app's settings and
click "Secrets." Add the following TOML-formatted block:

```toml
USDA_API_KEY = "your_usda_key_here"
FRED_API_KEY = "your_fred_key_here"
EIA_API_KEY  = "your_eia_key_here"
```

Streamlit Cloud injects these as environment variables at runtime.
The `python-dotenv` call in the code is a no-op in this environment,
which is the correct behavior.

### Step 5 — Verify deployment

After deployment (typically 2–5 minutes), your app will be available at:

```
https://your-username-harvest-squeeze-app-xxxxx.streamlit.app
```

The URL is shown in the Streamlit Cloud dashboard. Share this link for
portfolio or client demonstrations.

### Limitations on Community Cloud

- 1 GB RAM limit. The six-state national scan may be slow.
- GEE satellite data requires live authentication; use demo mode on Cloud.
- Apps sleep after 7 days of inactivity. The first visitor after sleep
  waits approximately 30 seconds for a cold start.

---

## 7. Docker Deployment

Docker provides a reproducible production environment for self-hosted
servers, cloud VMs, or enterprise deployments.

### Dockerfile

Create a file named `Dockerfile` in the project root:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# System dependencies for GeoPandas and Pydeck
RUN apt-get update && apt-get install -y \
    libgdal-dev \
    libproj-dev \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Pre-build the county centroid cache at image build time
RUN python build_centroids.py offline

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--server.fileWatcherType=none"]
```

### Build and run

```bash
# Build the image (takes 3–5 minutes on first build)
docker build -t harvest-squeeze:latest .

# Run with API keys injected at runtime
docker run -d \
  --name harvest-squeeze \
  -p 8501:8501 \
  -e USDA_API_KEY=your_key \
  -e FRED_API_KEY=your_key \
  -e EIA_API_KEY=your_key \
  harvest-squeeze:latest
```

The dashboard will be available at http://localhost:8501.

### Using a .env file with Docker

```bash
docker run -d \
  --name harvest-squeeze \
  -p 8501:8501 \
  --env-file .env \
  harvest-squeeze:latest
```

### Persist the centroid cache across container restarts

```bash
docker run -d \
  --name harvest-squeeze \
  -p 8501:8501 \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  harvest-squeeze:latest
```

This mounts the local `data/` directory so the parquet cache persists
even if the container is rebuilt.

### Docker Compose (recommended for production)

Create `docker-compose.yml`:

```yaml
version: "3.9"

services:
  harvest-squeeze:
    build: .
    image: harvest-squeeze:latest
    container_name: harvest-squeeze
    restart: unless-stopped
    ports:
      - "8501:8501"
    env_file:
      - .env
    volumes:
      - ./data:/app/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8501/_stcore/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

Run with:

```bash
docker compose up -d
```

---

## 8. Environment Variables Reference

| Variable          | Required | Description                                      |
|-------------------|----------|--------------------------------------------------|
| `USDA_API_KEY`    | Optional | USDA NASS QuickStats. Required for live yields.  |
| `FRED_API_KEY`    | Optional | FRED St. Louis Fed. Required for fertilizer PPI. |
| `EIA_API_KEY`     | Optional | EIA Energy. Required for live diesel price.      |
| `MANUAL_DIESEL`   | No       | Default diesel override when EIA key absent. Default: 3.82 |

All variables are optional in the sense that the application runs in demo mode
without them. Adding keys unlocks live USDA yield data, live FRED PPI, and
live EIA diesel prices.

---

## 9. Troubleshooting

### "USSoyValueChain.xlsx not found"

The XLSX file must be in the same directory as `app.py`. Verify:

```bash
ls -la USSoyValueChain.xlsx
```

If running from a different working directory, set the path in `config.py`:

```python
# config.py — ValueChainConfig
xlsx_path: str = "/absolute/path/to/USSoyValueChain.xlsx"
```

### "County centroids failed to load"

If the Census TIGER download fails (403 Forbidden, timeout, firewall):

```bash
python build_centroids.py offline
```

This builds the cache without any network access. The resulting centroids
are accurate to within 25–50 miles, which is appropriate for the logistics
model.

### Pydeck map is blank

Pydeck requires a Mapbox token for the `light-v11` style. Without a token,
the map tiles may not load in some environments. To fix:

1. Create a free Mapbox account at https://account.mapbox.com/
2. Copy your default public token.
3. Set it in `.env`: `MAPBOX_API_KEY=pk.ey...`
4. In `app.py`, pass the token to `pdk.Deck`:
   ```python
   pdk.Deck(..., api_keys={"mapbox": os.getenv("MAPBOX_API_KEY","")})
   ```

Alternatively, switch to an open tile style:

```python
map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
```

### USDA API returns no data

QuickStats can return empty responses when:

- The requested year has no finalized survey data (use 2023 or earlier).
- The state name is not in UPPERCASE (the API is case-sensitive).
- The API quota is exceeded (free tier: 50,000 requests/day).

Test your key directly:

```bash
curl "https://quickstats.nass.usda.gov/api/api_GET/?key=YOUR_KEY&commodity_desc=SOYBEANS&statisticcat_desc=YIELD&state_name=IOWA&year=2023&format=JSON&limit=3"
```

### GEE authentication errors

If `ee.Initialize()` fails with "Earth Engine client library not initialized":

1. Confirm you have run `ee.Authenticate()` at least once.
2. Check that the credentials file exists:
   - macOS/Linux: `~/.config/earthengine/credentials`
   - Windows: `C:\Users\YourName\.config\earthengine\credentials`
3. If the credentials are expired (they expire after 90 days), re-run
   `ee.Authenticate()`.

### Streamlit Cloud deployment is slow

The six-state national scan runs approximately 400 ms per state on Community
Cloud (vs. 80 ms locally). The `@st.cache_data` decorators ensure each
state is only computed once per session and cached for one hour. Subsequent
visits use cached results and load instantly.

### Docker build fails on GeoPandas

The GDAL system library is required. Ensure your Dockerfile includes:

```dockerfile
RUN apt-get update && apt-get install -y libgdal-dev libproj-dev gcc g++
```

On ARM64 hosts (Apple Silicon, AWS Graviton), build with:

```bash
docker buildx build --platform linux/amd64 -t harvest-squeeze:latest .
```

---

*The Harvest Squeeze — 2026 Planning Tool. Not investment advice.*
