# -*- coding: utf-8 -*-
from pathlib import Path

import pandas as pd
import geopandas as gpd

# ============================================================
# 設定
# ============================================================

TARGET_CRS = "EPSG:6676"

GPKG_PATH = Path(
    "/Users/tsg/Desktop/Ichinose_work/05_共滞在データのエンリッチメント/"
    "05_data/04_ボロノイ図/higashihiroshima_voronoi_v1.gpkg"
)

CELLS_LAYER = "voronoi_cells"

TRIPS_IN_PARQ = Path(
    "/Volumes/一ノ瀬/タッカー分解/ファイル/東広島滞在データ.parquet"
)

TRIPS_OUT_PARQ = Path(
    "/Volumes/一ノ瀬/タッカー分解/ファイル/東広島滞在データwith_building.parquet"
)

# ============================================================
# 1. Voronoi cells 読み込み
# ============================================================

cells = gpd.read_file(GPKG_PATH, layer=CELLS_LAYER)

print("cells columns:")
print(cells.columns.tolist())

# CRS確認
if cells.crs is None:
    raise ValueError("cells の CRS が未設定です。")

if str(cells.crs) != TARGET_CRS:
    cells = cells.to_crs(TARGET_CRS)

# site_id を building_id に変更
cells = cells.rename(columns={"site_id": "building_id"})

# 必要列だけ残す
cells_for_join = cells[["building_id", "building_name", "geometry"]].copy()

print("\nVoronoi cells 読み込み完了")
print(f"cells CRS: {cells_for_join.crs}")
print(f"cells数: {len(cells_for_join):,}")
print(f"building_nameありセル数: {cells_for_join['building_name'].notna().sum():,}")

# ============================================================
# 2. トリップデータ読み込み
# ============================================================

df = pd.read_parquet(TRIPS_IN_PARQ)

print("\nトリップデータ読み込み完了")
print(f"入力行数: {len(df):,}")
print(f"入力カラム数: {len(df.columns):,}")

required_cols = [
    "Latitude_start",
    "Latitude_end",
    "Longitude_start",
    "Longitude_end",
]

missing_cols = [col for col in required_cols if col not in df.columns]

if missing_cols:
    raise ValueError(f"入力 parquet に必要カラムがありません: {missing_cols}")

# ============================================================
# 3. 開始・終了座標から中点を作成
# ============================================================

lat_start = pd.to_numeric(df["Latitude_start"], errors="coerce")
lat_end = pd.to_numeric(df["Latitude_end"], errors="coerce")
lon_start = pd.to_numeric(df["Longitude_start"], errors="coerce")
lon_end = pd.to_numeric(df["Longitude_end"], errors="coerce")

lat_center = (lat_start + lat_end) / 2.0
lon_center = (lon_start + lon_end) / 2.0

df_out = df.copy()
df_out["Latitude_center"] = lat_center
df_out["Longitude_center"] = lon_center

valid_mask = (
    df_out["Latitude_center"].notna()
    & df_out["Longitude_center"].notna()
)

print("\n中点作成完了")
print(f"中点座標あり: {valid_mask.sum():,} / {len(df_out):,}")

# ============================================================
# 4. 中点を GeoDataFrame 化
# ============================================================

g_centers = gpd.GeoDataFrame(
    df_out.loc[valid_mask].copy(),
    geometry=gpd.points_from_xy(
        df_out.loc[valid_mask, "Longitude_center"],
        df_out.loc[valid_mask, "Latitude_center"]
    ),
    crs="EPSG:4326"
).to_crs(TARGET_CRS)

# ============================================================
# 5. 中点がどの Voronoi cell に入るか空間結合
# ============================================================

joined = gpd.sjoin(
    g_centers[["geometry"]],
    cells_for_join,
    how="left",
    predicate="within"
)

if "index_right" in joined.columns:
    joined = joined.drop(columns=["index_right"])

print("\n空間結合完了")
print(f"結合後行数: {len(joined):,}")
print(f"building_id ヒット数: {joined['building_id'].notna().sum():,}")
print(f"building_name ヒット数: {joined['building_name'].notna().sum():,}")

# ============================================================
# 6. 元データに building_id / building_name を付与
# ============================================================

df_out["building_id"] = pd.NA
df_out["building_name"] = pd.NA

df_out.loc[valid_mask, "building_id"] = joined["building_id"].to_numpy()
df_out.loc[valid_mask, "building_name"] = joined["building_name"].to_numpy()

# ============================================================
# 7. 保存
# ============================================================

TRIPS_OUT_PARQ.parent.mkdir(parents=True, exist_ok=True)

df_out.to_parquet(TRIPS_OUT_PARQ, index=False)

print("\n==============================")
print("OK: 出力完了")
print("==============================")
print(f"出力先: {TRIPS_OUT_PARQ}")
print(f"入力行数: {len(df_out):,}")
print(f"中点座標あり: {valid_mask.sum():,}")
print(f"building_id 付与数: {df_out['building_id'].notna().sum():,} / {len(df_out):,}")
print(f"building_name 付与数: {df_out['building_name'].notna().sum():,} / {len(df_out):,}")

if "TripMode" in df_out.columns:
    print("\nTripMode別件数:")
    print(df_out["TripMode"].value_counts(dropna=False))
