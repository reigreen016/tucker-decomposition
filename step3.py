from pathlib import Path
import pandas as pd
import geopandas as gpd
from tqdm import tqdm

# ============================================================
# 入力設定
# ============================================================

# GPS parquet ファイルが入っているディレクトリ
gps_dir = Path("/Volumes/一ノ瀬/共滞在アルバイト/GPS_data_with_socio")

# ポリゴンファイル
polygon_path = Path("/Volumes/一ノ瀬/共滞在アルバイト/東広島9つの町/r2kb34212_dissolved.shp")

# 出力先
out_path = Path("/Volumes/一ノ瀬/タッカー分解/ファイル/東広島滞在データ.parquet")

# GPSファイルの検索パターン
glob_pattern = "*.parquet"

# ============================================================
# ポリゴン読み込み
# ============================================================

polygon_gdf = gpd.read_file(polygon_path)

# GPS座標が WGS84 の場合
polygon_gdf = polygon_gdf.to_crs("EPSG:4326")

# 複数ポリゴンがある場合は1つに統合
target_polygon = polygon_gdf.geometry.union_all()

print("ポリゴン読み込み完了")
print(f"CRS: {polygon_gdf.crs}")
print(f"ポリゴン数: {len(polygon_gdf):,}")

# ============================================================
# GPSファイル一覧
# ============================================================

gps_files = sorted(gps_dir.glob(glob_pattern))

# Macの隠しファイルを除外
gps_files = [
    f for f in gps_files
    if not f.name.startswith("._")
]

print(f"対象GPSファイル数: {len(gps_files):,}")

# ============================================================
# 必要カラム
# ============================================================

use_cols = [
    "User_Id",
    "Trip_Id",
    "TripMode",
    "Time_start",
    "Time_end",
    "Latitude_start",
    "Latitude_end",
    "Longitude_start",
    "Longitude_end",
]

# ============================================================
# 抽出処理
# ============================================================

filtered_dfs = []

total_input_rows = 0
total_activity_rows = 0
total_extracted_rows = 0

for file in tqdm(gps_files, desc="Filtering GPS files"):

    try:
        # parquet 読み込み
        df = pd.read_parquet(file)

        total_input_rows += len(df)

        # 必要カラムが存在するか確認
        missing_cols = [col for col in use_cols if col not in df.columns]
        if missing_cols:
            print(f"スキップ: {file.name} に不足カラムあり: {missing_cols}")
            continue

        # 必要カラムのみ使用
        df = df[use_cols].copy()

        # TripMode = activity のみに絞る
        df = df[df["TripMode"] == "activity"].copy()

        total_activity_rows += len(df)

        if len(df) == 0:
            continue

        # 座標欠損を除外
        df = df.dropna(
            subset=[
                "Latitude_start",
                "Latitude_end",
                "Longitude_start",
                "Longitude_end",
            ]
        ).copy()

        if len(df) == 0:
            continue

        # ====================================================
        # 重要：indexをリセットする
        # ====================================================
        df = df.reset_index(drop=True)

        # 開始地点 Point
        start_points = gpd.GeoSeries(
            gpd.points_from_xy(
                df["Longitude_start"],
                df["Latitude_start"]
            ),
            crs="EPSG:4326",
            index=df.index
        )

        # 終了地点 Point
        end_points = gpd.GeoSeries(
            gpd.points_from_xy(
                df["Longitude_end"],
                df["Latitude_end"]
            ),
            crs="EPSG:4326",
            index=df.index
        )

        # ====================================================
        # 開始地点または終了地点がポリゴン内
        # ====================================================
        mask_start = start_points.within(target_polygon)
        mask_end = end_points.within(target_polygon)

        mask = mask_start | mask_end

        extracted = df.loc[mask].copy()

        if len(extracted) > 0:
            extracted["source_file"] = file.name
            filtered_dfs.append(extracted)
            total_extracted_rows += len(extracted)

    except Exception as e:
        print(f"エラー: {file.name}")
        print(e)

# ============================================================
# 結合して保存
# ============================================================

out_path.parent.mkdir(parents=True, exist_ok=True)

if filtered_dfs:
    result_df = pd.concat(filtered_dfs, ignore_index=True)

    result_df.to_parquet(out_path, index=False)

    print("\n==============================")
    print("保存完了")
    print("==============================")
    print(f"出力先: {out_path}")
    print(f"読み込み総行数: {total_input_rows:,}")
    print(f"activity行数: {total_activity_rows:,}")
    print(f"抽出行数: {len(result_df):,}")
    print(f"ユーザー数: {result_df['User_Id'].nunique():,}")
    print(f"元ファイル数: {result_df['source_file'].nunique():,}")

else:
    print("\n==============================")
    print("条件に一致するデータはありませんでした")
    print("==============================")
    print(f"読み込み総行数: {total_input_rows:,}")
    print(f"activity行数: {total_activity_rows:,}")
    print(f"抽出行数: {total_extracted_rows:,}")
