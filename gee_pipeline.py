"""
gee_pipeline.py
---------------
Google Earth Engine satellite data pipeline for The Harvest Squeeze.

Fetches two datasets that feed the yield modifier in the cost model:

  1. MODIS Terra MOD13A2
     NDVI 1km, 16-day composite. Peak growing season: June-August.
     High NDVI => healthy canopy => yield uplift.
     Low NDVI  => stress         => yield haircut.

  2. NASA SMAP 10km soil moisture
     ~3-day revisit. July peak-season observation.
     Drought (low SSM) or waterlogging (high SSM) => yield penalty.

Both datasets are sampled using buffered reduceRegion() calls at each
county centroid, then returned as DataFrames for merging into the model.

Authentication:
    One-time:  import ee; ee.Authenticate(); ee.Initialize()
    Then:      GEEPipeline().authenticate()

Demo mode:
    The page and CLI test run without GEE via synthetic data.
"""

import logging
import time
from typing import Optional
import json
import os
import ee
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# GEE collection identifiers
MODIS_NDVI   = "MODIS/061/MOD13A2"
SMAP_COLL    = "NASA_USDA/HSL/SMAP10KM_soil_moisture"
MODIS_SCALE  = 0.0001   # NDVI stored as integer * 10000

# Crop-specific growing season windows
GROWING_WINDOWS = {
    "soybean": {
        "early": (6,  6),    # June  — vegetative
        "peak":  (7,  8),    # Jul-Aug — R1/R2 critical window
        "late":  (9,  9),    # Sep   — maturity
    },
    "corn": {
        "early": (5,  6),    # May-Jun — V-stages
        "peak":  (7,  7),    # July  — VT/R1 critical
        "late":  (8,  9),    # Aug-Sep — grain fill
    },
}

NDVI_STRESS_THRESHOLD = 0.55   # below this = crop stress
NDVI_HEALTHY_MIN      = 0.55
NDVI_HEALTHY_MAX      = 0.85
SMAP_OPTIMAL_MIN      = 0.20   # m3/m3
SMAP_OPTIMAL_MAX      = 0.40


class GEEPipeline:
    """
    Manages Google Earth Engine API calls for satellite yield adjustment.

    Parameters
    ----------
    project_id : str, optional
        GEE cloud project ID. Leave None for personal unpaid accounts.
    buffer_m : int
        Circular buffer radius (m) around county centroid. Default 15 km.
    max_concurrent : int
        Max concurrent GEE requests (rate limit avoidance).
    retry_delay_s : float
        Seconds between retry attempts on GEE errors.
    """

    def __init__(
        self,
        project_id: Optional[str] = None,
        buffer_m: int = 15_000,
        max_concurrent: int = 5,
        retry_delay_s: float = 2.0,
    ):
        self.project_id     = project_id
        self.buffer_m       = buffer_m
        self.max_concurrent = max_concurrent
        self.retry_delay_s  = retry_delay_s
        self._ee            = None
        self._initialized   = False

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------


    def authenticate(self) -> bool:
        try:
            import streamlit as st

            creds_json = st.secrets.get("GEE_CREDENTIALS_JSON", None)

            if creds_json:
                creds_dict = json.loads(creds_json)

                credentials = ee.ServiceAccountCredentials(
                    creds_dict["client_email"],
                    key_data=creds_dict["private_key"]
                )

                ee.Initialize(credentials)
                logger.info("GEE initialized via Streamlit secrets")

            else:
                ee.Initialize()
                logger.warning("GEE initialized WITHOUT credentials (local mode)")

            self._ee = ee
            self._initialized = True
            return True

        except Exception as e:
            logger.error(f"GEE initialization failed: {e}")
            return False

    def _require_init(self) -> None:
        if not self._initialized:
            raise RuntimeError(
                "GEE not initialized. Call pipeline.authenticate() first."
            )

    def _buffer(self, lat: float, lon: float):
        return self._ee.Geometry.Point([lon, lat]).buffer(self.buffer_m)

    def _sample(self, image, geom, band: str, scale: int, retries: int = 3) -> Optional[float]:
        for attempt in range(1, retries + 1):
            try:
                val = (
                    image
                    .reduceRegion(
                        reducer=self._ee.Reducer.mean(),
                        geometry=geom,
                        scale=scale,
                        maxPixels=1e9,
                        bestEffort=True,
                    )
                    .getInfo()
                    .get(band)
                )
                return float(val) if val is not None else None
            except Exception:
                if attempt < retries:
                    time.sleep(self.retry_delay_s * attempt)
        return None

    # ------------------------------------------------------------------
    # NDVI fetch
    # ------------------------------------------------------------------

    def fetch_ndvi(
        self,
        fips_list: list,
        centroids_df: pd.DataFrame,
        year: int = 2025,
        crop: str = "soybean",
        season: str = "peak",
    ) -> pd.DataFrame:
        """
        Fetch MODIS NDVI mean for each county centroid.

        Parameters
        ----------
        fips_list : list of str
            5-digit FIPS codes.
        centroids_df : pd.DataFrame
            Must contain columns: fips_code, lat, lon.
        year : int
        crop : str   'soybean' or 'corn'
        season : str 'early', 'peak', or 'late'

        Returns
        -------
        pd.DataFrame
            Columns: fips_code, ndvi_mean, ndvi_z_score, ndvi_category.
        """
        self._require_init()
        ee = self._ee

        m_start, m_end = GROWING_WINDOWS[crop][season]
        collection = (
            ee.ImageCollection(MODIS_NDVI)
            .filterDate(f"{year}-{m_start:02d}-01", f"{year}-{m_end:02d}-28")
            .select("NDVI")
            .mean()
        )

        lookup = centroids_df.set_index("fips_code")
        results = []

        for i, fips in enumerate(fips_list):
            if fips not in lookup.index:
                continue
            row  = lookup.loc[fips]
            geom = self._buffer(row["lat"], row["lon"])
            raw  = self._sample(collection, geom, "NDVI", scale=1000)

            if raw is not None:
                results.append({"fips_code": fips, "ndvi_mean": raw * MODIS_SCALE})

            if (i + 1) % self.max_concurrent == 0:
                time.sleep(0.5)

        if not results:
            return pd.DataFrame(columns=["fips_code","ndvi_mean","ndvi_z_score","ndvi_category"])

        df = pd.DataFrame(results)
        mu, sigma = df["ndvi_mean"].mean(), df["ndvi_mean"].std()
        df["ndvi_z_score"] = (df["ndvi_mean"] - mu) / max(sigma, 0.001)
        df["ndvi_category"] = pd.cut(
            df["ndvi_mean"],
            bins=[-np.inf, 0.30, NDVI_HEALTHY_MIN, NDVI_HEALTHY_MAX, np.inf],
            labels=["Very Stressed", "Stressed", "Healthy", "Dense Canopy"],
        ).astype(str)

        logger.info(
            "NDVI fetched: %d counties | mean=%.3f", len(df), df["ndvi_mean"].mean()
        )
        return df

    # ------------------------------------------------------------------
    # SMAP fetch
    # ------------------------------------------------------------------

    def fetch_smap(
        self,
        fips_list: list,
        centroids_df: pd.DataFrame,
        year: int = 2025,
        month: int = 7,
    ) -> pd.DataFrame:
        """
        Fetch NASA SMAP surface soil moisture for each county centroid.

        Returns
        -------
        pd.DataFrame
            Columns: fips_code, smap_ssm_mean, smap_stress_flag.
        """
        self._require_init()
        ee = self._ee

        collection = (
            ee.ImageCollection(SMAP_COLL)
            .filterDate(f"{year}-{month:02d}-01", f"{year}-{month:02d}-28")
            .select("ssm")
            .mean()
        )

        lookup  = centroids_df.set_index("fips_code")
        results = []

        for i, fips in enumerate(fips_list):
            if fips not in lookup.index:
                continue
            row  = lookup.loc[fips]
            geom = self._buffer(row["lat"], row["lon"])
            ssm  = self._sample(collection, geom, "ssm", scale=10_000)

            if ssm is not None:
                results.append({"fips_code": fips, "smap_ssm_mean": float(ssm)})

            if (i + 1) % self.max_concurrent == 0:
                time.sleep(0.5)

        if not results:
            return pd.DataFrame(columns=["fips_code","smap_ssm_mean","smap_stress_flag"])

        df = pd.DataFrame(results)
        df["smap_stress_flag"] = np.select(
            [
                df["smap_ssm_mean"] < 0.10,
                df["smap_ssm_mean"] < SMAP_OPTIMAL_MIN,
                df["smap_ssm_mean"] > 0.50,
                df["smap_ssm_mean"] > SMAP_OPTIMAL_MAX,
            ],
            ["SEVERE DROUGHT", "DRY STRESS", "WATERLOGGED", "WET STRESS"],
            default="OPTIMAL",
        )

        logger.info(
            "SMAP fetched: %d counties | mean SSM=%.3f", len(df), df["smap_ssm_mean"].mean()
        )
        return df

    # ------------------------------------------------------------------
    # Composite fetch
    # ------------------------------------------------------------------

    def fetch_all(
        self,
        fips_list: list,
        centroids_df: pd.DataFrame,
        year: int = 2025,
        crop: str = "soybean",
    ) -> dict:
        """
        Fetch NDVI (peak + early season) and SMAP in one call.

        Returns
        -------
        dict
            Keys: 'ndvi_peak', 'ndvi_early', 'smap', 'combined'.
        """
        self._require_init()

        logger.info(
            "GEE full fetch | crop=%s | year=%d | n=%d counties",
            crop, year, len(fips_list),
        )

        ndvi_peak  = self.fetch_ndvi(fips_list, centroids_df, year, crop, "peak")
        ndvi_early = self.fetch_ndvi(fips_list, centroids_df, year, crop, "early")
        smap       = self.fetch_smap(fips_list, centroids_df, year, month=7)

        combined = ndvi_peak[["fips_code","ndvi_mean","ndvi_z_score","ndvi_category"]].copy()

        if not ndvi_early.empty:
            combined = combined.merge(
                ndvi_early[["fips_code","ndvi_mean"]].rename(
                    columns={"ndvi_mean": "ndvi_early_mean"}
                ),
                on="fips_code", how="left",
            )

        if not smap.empty:
            combined = combined.merge(
                smap[["fips_code","smap_ssm_mean","smap_stress_flag"]],
                on="fips_code", how="left",
            )

        return {
            "ndvi_peak":  ndvi_peak,
            "ndvi_early": ndvi_early,
            "smap":       smap,
            "combined":   combined,
        }

    # ------------------------------------------------------------------
    # Yield modifier
    # ------------------------------------------------------------------

    def build_yield_modifiers(
        self,
        satellite_df: pd.DataFrame,
        crop: str = "soybean",
    ) -> pd.DataFrame:
        """
        Convert satellite metrics into per-county yield modifier factors.

        Modifier range: 0.70 to 1.25 (i.e. -30% to +25% vs. trend yield).

        Logic:
          ndvi_z > +1.5  => +15%
          ndvi_z > +0.5  => +7%
          ndvi_z neutral => baseline
          ndvi_z < -0.5  => -8%
          ndvi_z < -1.5  => -18%
          SEVERE DROUGHT => additional -12%

        Returns
        -------
        pd.DataFrame
            Columns: fips_code, yield_modifier, yield_adj_notes.
        """
        if satellite_df.empty:
            return pd.DataFrame(columns=["fips_code","yield_modifier"])

        df   = satellite_df.copy()
        ndvi = df.get("ndvi_z_score", pd.Series(0.0, index=df.index))

        ndvi_mod = np.select(
            [ndvi > 1.5, ndvi > 0.5, ndvi < -1.5, ndvi < -0.5],
            [1.15, 1.07, 0.82, 0.92],
            default=1.0,
        )

        smap_map = {
            "OPTIMAL": 1.00, "WET STRESS": 0.97,
            "DRY STRESS": 0.93, "SEVERE DROUGHT": 0.88, "WATERLOGGED": 0.91,
        }
        smap_flag = df.get("smap_stress_flag", pd.Series("OPTIMAL", index=df.index))
        smap_mod  = smap_flag.map(smap_map).fillna(1.0).values

        df["yield_modifier"] = np.clip(ndvi_mod * smap_mod, 0.70, 1.25)

        def _note(row):
            parts = []
            nz = row.get("ndvi_z_score", 0)
            if isinstance(nz, (int, float)):
                if nz > 1.0:
                    parts.append("strong canopy")
                elif nz < -1.0:
                    parts.append("weak canopy")
            sf = row.get("smap_stress_flag", "OPTIMAL")
            if sf != "OPTIMAL":
                parts.append(sf.lower())
            return "; ".join(parts) if parts else "baseline"
        df["yield_adj_notes"] = df.apply(_note, axis=1)
        return df[["fips_code","yield_modifier","yield_adj_notes"]].copy()


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n" + "=" * 56)
    print("  GEE Pipeline Test")
    print("=" * 56)

    pipeline = GEEPipeline()
    ok = pipeline.authenticate()

    if not ok:
        print("\nGEE not authenticated.")
        print("Run this once in a terminal:")
        print("  import ee; ee.Authenticate(); ee.Initialize()")
        print("\nThe rest of the model (spatial + cost) runs without GEE.")
        print("GEE is used only for the Satellite View page yield modifiers.")
    else:
        from data_acquisition import load_county_centroids
        cent  = load_county_centroids()
        iowa  = cent[cent["state_fips"] == "19"].head(8)
        fips  = iowa["fips_code"].tolist()

        print(f"\nTesting {len(fips)} Iowa counties...")
        ndvi = pipeline.fetch_ndvi(fips, iowa, year=2025, crop="soybean", season="peak")
        smap = pipeline.fetch_smap(fips, iowa, year=2025, month=7)

        print("\nNDVI results:")
        print(ndvi[["fips_code","ndvi_mean","ndvi_z_score","ndvi_category"]].to_string(index=False))

        print("\nSMAP results:")
        print(smap[["fips_code","smap_ssm_mean","smap_stress_flag"]].to_string(index=False))

        combined  = ndvi.merge(smap, on="fips_code", how="left")
        modifiers = pipeline.build_yield_modifiers(combined)
        print("\nYield modifiers:")
        print(modifiers.to_string(index=False))

    print("\n" + "=" * 56 + "\n")
