from pathlib import Path
import pandas as pd
from tqdm import tqdm

# ============================================================
# 入力
# ============================================================

# 元のGPSデータ群が入っているフォルダ
gps_dir = Path(
    "/Volumes/一ノ瀬/09_共滞在アルバイト/01_【第1層】下処理（Preprocessing）コードの整理/01_本番/出力_20260604/step2_daily"
)

# 全ユーザー情報ファイル
user_info_path = Path(
    "/Volumes/一ノ瀬/09_共滞在アルバイト/ユーザー情報/all_users_info.parquet"
)

# 出力先フォルダ
out_dir = Path(
    "/Volumes/一ノ瀬/09_共滞在アルバイト/GPS_data_with_socio"
)

out_dir.mkdir(parents=True, exist_ok=True)

# ============================================================
# 全ユーザー情報ファイルを読み込み
# ============================================================

user_info_df = pd.read_parquet(user_info_path)

print("ユーザー情報ファイル")
print(f"行数: {len(user_info_df):,}")
print(f"ユニークユーザー数: {user_info_df['User_Id'].nunique():,}")
print(user_info_df.columns.tolist())

# 念のため User_Id の重複を除去
user_info_df = user_info_df.drop_duplicates(subset=["User_Id"])

# ============================================================
# 元GPSデータ群を取得
# ============================================================

parquet_files = sorted(gps_dir.glob("*.parquet"))

print(f"処理対象GPSファイル数: {len(parquet_files)}")

# ============================================================
# 各GPSファイルにユーザー情報を結合して保存
# ============================================================

for file in tqdm(parquet_files, desc="Merging user info"):

    gps_df = pd.read_parquet(file)

    before_rows = len(gps_df)

    # User_Id が存在するか確認
    if "User_Id" not in gps_df.columns:
        print(f"スキップ: User_Id が存在しません: {file.name}")
        continue

    # User_Idで結合
    merged_df = gps_df.merge(
        user_info_df,
        on="User_Id",
        how="left"
    )

    after_rows = len(merged_df)

    # 行数が変わっていないか確認
    if before_rows != after_rows:
        print(f"注意: 行数が変化しました: {file.name}")
        print(f"before: {before_rows:,}, after: {after_rows:,}")

    # 保存
    out_path = out_dir / file.name
    merged_df.to_parquet(out_path, index=False)

print("================================")
print("保存完了")
print("================================")
print(f"保存先フォルダ: {out_dir}")
