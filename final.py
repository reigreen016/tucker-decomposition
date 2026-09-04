# ============================================================
# Non-negative Tucker Decomposition
# Tensor: TimeSlot144 × User × BuildingName
# Rule:
#   - 10分スロットに格納
#   - 10分のうち8分以上トリップが確認される場合のみ採用
#   - 日付は捨てて、1日の中の144スロットに集約
# ============================================================

import pandas as pd
import numpy as np
import tensorly as tl
from sparse import COO
from tensorly.decomposition import non_negative_tucker
from pathlib import Path
from datetime import datetime

# ============================================================
# 0) 入力・出力設定
# ============================================================

INPUT_PARQUET = "/Volumes/一ノ瀬/タッカー分解/ファイル/東広島滞在データwith_building.parquet"

INPUT_NAMES_CSV = "/Users/tsg/Desktop/Ichinose_work/05_共滞在データのエンリッチメント/05_data/02_広島県土地利用データ/Saijo500m_with_counts.csv"

OUT_DIR = Path("/Volumes/一ノ瀬/タッカー分解/出力/tucker分解")
OUT_DIR.mkdir(parents=True, exist_ok=True)

USER_COL = "User_Id"
START_COL = "Time_start"
END_COL = "Time_end"
BUILDING_COL = "building_name"

SLOT_WIDTH = "10min"
MIN_OVERLAP = pd.Timedelta("8min")

# X.shape = (144, U, B)
# TUCKER_RANK = (時間成分数, ユーザー成分数, 建物成分数)
TUCKER_RANK = (6, 8, 6)

N_ITER_MAX = 300
TOL = 1e-6
RANDOM_STATE = 0

tl.set_backend("numpy")


# ============================================================
# 1) ユーティリティ関数
# ============================================================

def try_read_csv(path: str) -> pd.DataFrame:
    # 日本語CSVの文字コード対策
    for enc in ["utf-8-sig", "cp932", "shift_jis", "utf-8"]:
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception:
            pass
    return pd.read_csv(path)


def normalize_name(s: pd.Series) -> pd.Series:
    # 建物名の表記揺れを軽く補正する
    s2 = s.astype("string").fillna("")
    s2 = s2.str.replace("\u3000", " ", regex=False)
    s2 = s2.str.strip().str.replace(r"\s+", " ", regex=True)
    return s2


def make_144_time_labels():
    # 00:00, 00:10, ..., 23:50 の144ラベルを作る
    labels = []
    for h in range(24):
        for m in range(0, 60, 10):
            labels.append(f"{h:02d}:{m:02d}")
    return labels


def l1_cols(A, eps=1e-12):
    # 各列の和が1になるように正規化
    A = np.asarray(A, dtype=np.float32)
    s = A.sum(axis=0, keepdims=True) + eps
    return A / s


def topk(names, w, k=10):
    # 重みが大きい上位k個を返す
    w = np.asarray(w, dtype=float).ravel()
    idx = np.argsort(-w)[:k]
    return [(str(names[i]), float(w[i])) for i in idx]


def show_top(df, comp, k=20, title=""):
    # 因子行列の上位要素を表示
    top = df.sort_values(comp, ascending=False).head(k)
    print(f"\n[{title} × {comp}] top-{k}")
    print(top[[comp]].to_string())


# ============================================================
# 2) 対象建物名CSVの読み込み
# ============================================================

names_df = try_read_csv(INPUT_NAMES_CSV)

name_col_candidates = [
    c for c in names_df.columns
    if any(k in c.lower() for k in ["建物", "名称", "施設", "name"])
]

if not name_col_candidates:
    raise KeyError("建物名列がCSVに見つかりません。例: '建物名', '名称', '施設名', 'name'")

names_col = name_col_candidates[0]

names_df["_name_key"] = normalize_name(names_df[names_col])
valid_name_keys = set(names_df["_name_key"].dropna().unique())

print("========== 対象建物CSV ==========")
print(f"建物名列: {names_col}")
print(f"対象建物数: {len(valid_name_keys):,}")


# ============================================================
# 3) Parquet読み込み
# ============================================================

df = pd.read_parquet(INPUT_PARQUET)

print("\n========== Parquet読み込み ==========")
print(f"読み込み直後 行数: {len(df):,}")
print(f"列数: {df.shape[1]:,}")

required_cols = [
    USER_COL,
    START_COL,
    END_COL,
    BUILDING_COL,
]

missing_cols = [c for c in required_cols if c not in df.columns]

if missing_cols:
    raise KeyError(f"必要なカラムがありません: {missing_cols}")


# ============================================================
# 4) 必要カラムだけ残す
# ============================================================

use_cols = [
    USER_COL,
    "Trip_Id",
    "TripMode",
    START_COL,
    END_COL,
    "Latitude_start",
    "Latitude_end",
    "Longitude_start",
    "Longitude_end",
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
    "source_file",
    "Latitude_center",
    "Longitude_center",
    "building_id",
    BUILDING_COL,
]

use_cols = [c for c in use_cols if c in df.columns]
df = df[use_cols].copy()

print("\n========== 使用カラム ==========")
print(df.columns.tolist())


# ============================================================
# 5) 建物名フィルタ
# ============================================================

df["_name_key"] = normalize_name(df[BUILDING_COL])
df = df[df["_name_key"].isin(valid_name_keys)].copy()

print("\n========== 建物フィルタ ==========")
print(f"対象建物フィルタ後 行数: {len(df):,}")


# ============================================================
# 6) 時刻処理・欠損処理・activity抽出
# ============================================================

df[START_COL] = pd.to_datetime(df[START_COL], errors="coerce")
df[END_COL] = pd.to_datetime(df[END_COL], errors="coerce")

df = df.dropna(subset=[USER_COL, START_COL, END_COL, BUILDING_COL])
df = df[df[END_COL] > df[START_COL]].copy()

if "TripMode" in df.columns:
    before = len(df)
    df = df[df["TripMode"].eq("activity")].copy()

    print("\n========== TripMode filter ==========")
    print(f"activity抽出前: {before:,}")
    print(f"activity抽出後: {len(df):,}")

df["B_building"] = df[BUILDING_COL].astype("string").fillna("(不明)").str.strip()

print("\n========== 有効トリップ ==========")
print(f"有効トリップ数: {len(df):,}")
print(f"ユニークユーザー数: {df[USER_COL].nunique():,}")
print(f"ユニーク建物数: {df['B_building'].nunique():,}")


# ============================================================
# 7) 各トリップを10分スロット候補に展開
# ============================================================

slot_td = pd.Timedelta(SLOT_WIDTH)

df["_slot_start_min"] = df[START_COL].dt.floor(SLOT_WIDTH)

df["_slot_start_max"] = (
    df[END_COL] - pd.Timedelta("1ns")
).dt.floor(SLOT_WIDTH)

df["_n_slots"] = (
    (df["_slot_start_max"] - df["_slot_start_min"]) / slot_td
).astype(int) + 1

df = df[df["_n_slots"] > 0].copy()

print("\n========== 10分スロット展開 ==========")
print(f"展開前トリップ数: {len(df):,}")
print(f"展開後の想定行数: {df['_n_slots'].sum():,}")
print(f"最大スロット数/トリップ: {df['_n_slots'].max():,}")

df["_slot_offsets"] = df["_n_slots"].apply(
    lambda n: np.arange(n, dtype=np.int32)
)

slot_df = df.explode("_slot_offsets", ignore_index=True)
slot_df["_slot_offsets"] = slot_df["_slot_offsets"].astype(np.int32)

slot_df["time_slot_dt"] = (
    slot_df["_slot_start_min"] +
    slot_df["_slot_offsets"] * slot_td
)

slot_df["slot_end"] = slot_df["time_slot_dt"] + slot_td

print(f"実際の展開後行数: {len(slot_df):,}")


# ============================================================
# 8) 各10分スロットとの重なり時間を計算
# ============================================================

overlap_start = slot_df[[START_COL, "time_slot_dt"]].max(axis=1)
overlap_end = slot_df[[END_COL, "slot_end"]].min(axis=1)

slot_df["overlap"] = overlap_end - overlap_start

slot_df = slot_df[slot_df["overlap"] >= MIN_OVERLAP].copy()

print("\n========== 8分以上重なるスロットのみ採用 ==========")
print(f"採用スロット行数: {len(slot_df):,}")
print(f"ユニークユーザー数: {slot_df[USER_COL].nunique():,}")
print(f"ユニーク建物数: {slot_df['B_building'].nunique():,}")


# ============================================================
# 9) 日付を捨てて、1日144個の10分スロットに集約
# ============================================================

slot_df["time_slot_id"] = (
    slot_df["time_slot_dt"].dt.hour * 6 +
    slot_df["time_slot_dt"].dt.minute // 10
).astype(np.int16)

slot_df["time_slot_label"] = slot_df["time_slot_dt"].dt.strftime("%H:%M")

T_labels = make_144_time_labels()

print("\n========== 144時間スロット化 ==========")
print(f"time_slot_id min: {slot_df['time_slot_id'].min()}")
print(f"time_slot_id max: {slot_df['time_slot_id'].max()}")
print(f"ユニーク time_slot_id 数: {slot_df['time_slot_id'].nunique():,}")
print(f"T_labels 数: {len(T_labels)}")


# ============================================================
# 10) ユーザー・建物軸をカテゴリ化
# ============================================================

slot_df[USER_COL] = slot_df[USER_COL].astype("category")
slot_df["B_building"] = slot_df["B_building"].astype("category")

U_labels = list(slot_df[USER_COL].cat.categories)
B_labels = list(slot_df["B_building"].cat.categories)

T = 144
U = len(U_labels)
B = len(B_labels)

print("\n========== テンソルサイズ ==========")
print(f"X.shape = ({T:,}, {U:,}, {B:,})")
print(f"Tucker rank = {TUCKER_RANK}")

dense_size_gb = T * U * B * 4 / 1e9
print(f"Dense tensor float32 推定サイズ: {dense_size_gb:.2f} GB")


# ============================================================
# 11) COO座標を作成
# ============================================================

t_codes = slot_df["time_slot_id"].to_numpy(np.int64)
u_codes = slot_df[USER_COL].cat.codes.to_numpy(np.int64)
b_codes = slot_df["B_building"].cat.codes.to_numpy(np.int64)

mask = (
    (t_codes >= 0) &
    (t_codes < 144) &
    (u_codes >= 0) &
    (b_codes >= 0)
)

coords_raw = np.vstack([
    t_codes[mask],
    u_codes[mask],
    b_codes[mask],
])

triplets = coords_raw.T

uniq, inv = np.unique(triplets, axis=0, return_inverse=True)
values = np.bincount(inv).astype(np.float32)
coords = uniq.T

print("\n========== COO座標 ==========")
print(f"非ゼロ要素数 nnz: {len(values):,}")
print(f"value min: {values.min():.0f}")
print(f"value max: {values.max():.0f}")
print(f"value mean: {values.mean():.4f}")


# ============================================================
# 12) 疎テンソル作成
# ============================================================

X_sparse = COO(
    coords,
    values,
    shape=(T, U, B),
).astype(np.float32)

print("\n========== 疎テンソル ==========")
print(f"X_sparse.shape = {X_sparse.shape}")
print(f"X_sparse.nnz = {X_sparse.nnz:,}")


# ============================================================
# 13) dense化
# ============================================================

print("\n========== dense tensor 変換 ==========")
print("dense tensorに変換します")

X_dense = X_sparse.todense().astype(np.float32)

print("dense化完了")
print(f"X_dense.shape = {X_dense.shape}")
print(f"X_dense dtype = {X_dense.dtype}")
print(f"X_dense size = {X_dense.nbytes / 1e9:.2f} GB")


# ============================================================
# 14) 非負Tucker分解
# ============================================================

print("\n========== 非負Tucker分解 ==========")
print("非負Tucker分解を開始します")

result = non_negative_tucker(
    X_dense,
    rank=TUCKER_RANK,
    n_iter_max=N_ITER_MAX,
    tol=TOL,
    init="random",
    random_state=RANDOM_STATE,
    verbose=True,
)

errors = None

if isinstance(result, tuple):
    if len(result) == 3:
        core, factors, errors = result
    elif len(result) == 2:
        core, factors = result
    else:
        raise ValueError(
            f"non_negative_tucker のtuple戻り値の長さが想定外です: {len(result)}"
        )

elif hasattr(result, "core") and hasattr(result, "factors"):
    core = result.core
    factors = result.factors

else:
    raise ValueError(
        f"non_negative_tucker の戻り値の形式が想定外です: {type(result)}"
    )

T_fac, U_fac, B_fac = factors

core_arr = np.asarray(core, dtype=np.float32)
T_fac = np.asarray(T_fac, dtype=np.float32)
U_fac = np.asarray(U_fac, dtype=np.float32)
B_fac = np.asarray(B_fac, dtype=np.float32)

print("\nTucker分解完了")
print(f"core.shape = {core_arr.shape}")
print(f"T_fac.shape = {T_fac.shape}")
print(f"U_fac.shape = {U_fac.shape}")
print(f"B_fac.shape = {B_fac.shape}")

if errors is not None:
    print(f"iters = {len(errors)}")
    print(f"last_error = {errors[-1]:.6f}")
else:
    print("errors は取得されませんでした。TensorLyの戻り値仕様によるものです。")


# ============================================================
# 15) 因子行列をDataFrame化
# ============================================================

T_rank, U_rank, B_rank = TUCKER_RANK

T_cols = [f"T_comp{r+1}" for r in range(T_rank)]
U_cols = [f"U_comp{r+1}" for r in range(U_rank)]
B_cols = [f"B_comp{r+1}" for r in range(B_rank)]

T_df = pd.DataFrame(
    T_fac,
    index=T_labels,
    columns=T_cols,
)

U_df = pd.DataFrame(
    U_fac,
    index=U_labels,
    columns=U_cols,
)

B_df = pd.DataFrame(
    B_fac,
    index=B_labels,
    columns=B_cols,
)

print("\n========== 因子行列 ==========")
print("T_df:", T_df.shape)
print("U_df:", U_df.shape)
print("B_df:", B_df.shape)


# ============================================================
# 16) core tensorをlong形式に変換
# ============================================================

core_rows = []

for i in range(core_arr.shape[0]):
    for j in range(core_arr.shape[1]):
        for k in range(core_arr.shape[2]):
            core_rows.append({
                "T_component": f"T_comp{i+1}",
                "U_component": f"U_comp{j+1}",
                "B_component": f"B_comp{k+1}",
                "core_value": float(core_arr[i, j, k]),
            })

core_df = pd.DataFrame(core_rows)
core_df = core_df.sort_values("core_value", ascending=False).reset_index(drop=True)

print("\n========== Core tensor 上位 ==========")
display(core_df.head(20))


# ============================================================
# 17) 保存
# ============================================================

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

T_path = OUT_DIR / "tucker_T_144_time_factors.csv"
U_path = OUT_DIR / "tucker_U_user_factors.csv"
B_path = OUT_DIR / "tucker_B_building_factors.csv"
core_path = OUT_DIR / "tucker_core_tensor.csv"
summary_path = OUT_DIR / "tucker_component_summary.json"

T_df.to_csv(T_path, encoding="utf-8-sig")
U_df.to_csv(U_path, encoding="utf-8-sig")
B_df.to_csv(B_path, encoding="utf-8-sig")
core_df.to_csv(core_path, index=False, encoding="utf-8-sig")

time_label_df = pd.DataFrame({
    "time_slot_id": np.arange(144),
    "time_slot_label": T_labels,
})

time_label_df.to_csv(
    OUT_DIR / "time_slot_144_labels.csv",
    index=False,
    encoding="utf-8-sig",
)

print("\n========== 保存完了 ==========")
print(f"saved: {T_path}")
print(f"saved: {U_path}")
print(f"saved: {B_path}")
print(f"saved: {core_path}")


# ============================================================
# 18) 各因子の上位要素表示
# ============================================================

print("\n========== Time factor 上位 ==========")
for comp in T_cols:
    show_top(T_df, comp, k=20, title="TimeSlot")

print("\n========== User factor 上位 ==========")
for comp in U_cols:
    show_top(U_df, comp, k=10, title="User")

print("\n========== Building factor 上位 ==========")
for comp in B_cols:
    show_top(B_df, comp, k=20, title="Building")


# ============================================================
# 19) 解釈用サマリ作成
# ============================================================

T_l1 = l1_cols(T_df.values)
U_l1 = l1_cols(U_df.values)
B_l1 = l1_cols(B_df.values)

summary_rows = []

for _, row in core_df.head(20).iterrows():
    t_comp = row["T_component"]
    u_comp = row["U_component"]
    b_comp = row["B_component"]

    t_idx = T_cols.index(t_comp)
    u_idx = U_cols.index(u_comp)
    b_idx = B_cols.index(b_comp)

    summary_rows.append({
        "T_component": t_comp,
        "U_component": u_comp,
        "B_component": b_comp,
        "core_value": row["core_value"],
        "top_time_slots": topk(T_df.index.tolist(), T_l1[:, t_idx], 10),
        "top_users": topk(U_df.index.tolist(), U_l1[:, u_idx], 5),
        "top_buildings": topk(B_df.index.tolist(), B_l1[:, b_idx], 10),
    })

summary_df = pd.DataFrame(summary_rows)

summary_df.to_json(
    summary_path,
    orient="records",
    force_ascii=False,
    indent=2,
)

print("\n========== Tucker component summary ==========")
print(f"saved: {summary_path}")
display(summary_df.head(10))


# ============================================================
# 20) ユーザー属性とU因子を結合して保存
# ============================================================

user_attr_cols = [
    USER_COL,
    "gender",
    "age_group",
    "device_os",
    "Home_Latitude",
    "Home_Longitude",
    "Office_Latitude",
    "Office_Longitude",
]

user_attr_cols = [c for c in user_attr_cols if c in df.columns]

if len(user_attr_cols) > 1:
    user_attr_df = (
        df[user_attr_cols]
        .drop_duplicates(subset=[USER_COL])
        .set_index(USER_COL)
    )

    U_with_attr_df = U_df.join(user_attr_df, how="left")

    U_with_attr_path = OUT_DIR / "tucker_U_user_factors_with_attributes.csv"
    U_with_attr_df.to_csv(U_with_attr_path, encoding="utf-8-sig")

    print("\n========== User factor + attributes ==========")
    print(f"saved: {U_with_attr_path}")
    print(U_with_attr_df.head())


# ============================================================
# 21) 完了
# ============================================================

print("\n========== ALL DONE ==========")
print("Tucker decomposition finished successfully.")
