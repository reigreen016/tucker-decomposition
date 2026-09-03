from pathlib import Path
import pandas as pd
from tqdm import tqdm

# ============================================================
# 入力フォルダ
# ============================================================
in_dir = Path("/Users/tsg/Desktop/watanabe_work/trips_cleaning/users_merge_home_office_location")

parquet_files = sorted(in_dir.glob("*.parquet"))

print(f"parquetファイル数: {len(parquet_files)}")

# ============================================================
# 使用するカラム
# ============================================================
use_cols = [
    "hashed_user_id",
    "gender",
    "age_group",
    "device_os",
    "device_model",
    "device_os_version",
    "device_carrier",
    "ip_address",
    "Home_Latitude",
    "Home_Longitude",
    "Office_Latitude",
    "Office_Longitude",
]

# ============================================================
# 全parquetを読み込み
# ============================================================
dfs = []

for file in tqdm(parquet_files, desc="Reading parquet files"):
    df = pd.read_parquet(file, columns=use_cols)
    dfs.append(df)

all_df = pd.concat(dfs, ignore_index=True)

print("読み込み完了")
print(f"全行数: {len(all_df):,}")
print(f"ユニークユーザー数: {all_df['hashed_user_id'].nunique():,}")

# ============================================================
# ユーザー単位に1行へ集約
# ============================================================
# 同じユーザーが複数ファイル・複数行に存在する可能性があるため、
# 各ユーザーについて最初に見つかった非欠損値を採用する
user_df = (
    all_df
    .groupby("hashed_user_id", as_index=False)
    .first()
)

# hashed_user_id → User_Id に変更
user_df = user_df.rename(columns={"hashed_user_id": "User_Id"})

# カラム順を整理
out_cols = [
    "User_Id",
    "gender",
    "age_group",
    "device_os",
    "device_model",
    "device_os_version",
    "device_carrier",
    "ip_address",
    "Home_Latitude",
    "Home_Longitude",
    "Office_Latitude",
    "Office_Longitude",
]

user_df = user_df[out_cols]

print("================================")
print("全ユーザー情報")
print("================================")
print(f"全ユーザー数: {len(user_df):,}")

# ============================================================
# 4情報ありユーザーを抽出
# 家・職場・年齢・性別がすべてあるユーザー
# ============================================================
required_cols = [
    "gender",
    "age_group",
    "Home_Latitude",
    "Home_Longitude",
    "Office_Latitude",
    "Office_Longitude",
]

complete_user_df = user_df.dropna(subset=required_cols).copy()

print("================================")
print("4情報ありユーザー情報")
print("================================")
print(f"4情報ありユーザー数: {len(complete_user_df):,}")
print(f"割合: {len(complete_user_df) / len(user_df) * 100:.2f}%")

# ============================================================
# 保存
# ============================================================
out_all_path = "/Volumes/一ノ瀬/09_共滞在アルバイト/ユーザー情報/all_users_info.parquet"
out_complete_path = "/Volumes/一ノ瀬/09_共滞在アルバイト/ユーザー情報/users_with_home_office_age_gender_info.parquet"

user_df.to_parquet(out_all_path, index=False)
complete_user_df.to_parquet(out_complete_path, index=False)

print("================================")
print("保存完了")
print("================================")
print(f"全ユーザー情報ファイル: {out_all_path}")
print(f"4情報ありユーザー情報ファイル: {out_complete_path}")
