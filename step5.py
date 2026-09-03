import pandas as pd
import numpy as np
from tqdm import tqdm

def keep_overlaps_5min_fast_allcols(
    df,
    user_col="User_Id",
    bname_col="building_name",
    s_col="Time_start",
    e_col="Time_end",
    min_ov="5min",
):
    """
    同一 building_name 内で別ユーザーと5分以上重なったトリップのみ残す（高速・全カラム保持）
    返り値は元dfのカラムを全て含み、building_name→t_startでソート済み。
    """
    MIN_OV = pd.Timedelta(min_ov)

    # ---- 下ごしらえ（元カラム保持）----
    x = df.copy()
    x[s_col] = pd.to_datetime(x[s_col], errors="coerce")
    x[e_col] = pd.to_datetime(x[e_col], errors="coerce")

    # 有効行（NaTや負の区間を除外、かつ自身が5分未満は除外）
    valid = (
        x[bname_col].notna()
        & x[s_col].notna()
        & x[e_col].notna()
        & (x[e_col] > x[s_col])
        & ((x[e_col] - x[s_col]) >= MIN_OV)
    )
    x = x.loc[valid].copy()

    # groupby 高速化
    x[bname_col] = x[bname_col].astype("category")

    # 要求どおり building_name → t_start で安定ソート
    x = x.sort_values([bname_col, s_col], kind="mergesort")

    # keep フラグは x のインデックスに対して持つ（最後に x[keep] を df へ戻す）
    keep = pd.Series(False, index=x.index)

    # ---- 建物ごとに一次スキャン（高速）----
    for _, g in tqdm(x.groupby(bname_col, sort=False), desc="buildings"):
        idx = g.index.to_numpy()
        s   = g[s_col].to_numpy(dtype="datetime64[ns]")
        e   = g[e_col].to_numpy(dtype="datetime64[ns]")
        u   = g[user_col].to_numpy()

        # アクティブ集合（end昇順を維持）
        a_idx = np.empty(0, dtype=idx.dtype)
        a_s   = np.empty(0, dtype="datetime64[ns]")
        a_e   = np.empty(0, dtype="datetime64[ns]")
        a_u   = np.empty(0, dtype=object)

        min_ov_ns = np.timedelta64(int(MIN_OV.value), "ns")

        for i in range(len(g)):
            si, ei, ui, idx_i = s[i], e[i], u[i], idx[i]

            # これ以降と5分以上重ならない区間を削除: end < si + MIN_OV
            cut = si + min_ov_ns
            if a_e.size:
                mask = (a_e >= cut)
                if mask.any():
                    if (~mask).any():
                        a_idx = a_idx[mask]; a_s = a_s[mask]
                        a_e   = a_e[mask];   a_u = a_u[mask]
                else:
                    # 全部捨てる
                    a_idx = a_idx[:0]; a_s = a_s[:0]; a_e = a_e[:0]; a_u = a_u[:0]

            # 重なり長（ベクトル）: min(ei, a_e) - max(si, a_s)
            if a_idx.size:
                ov = np.minimum(ei, a_e) - np.maximum(si, a_s)
                ok = (a_u != ui) & (ov >= min_ov_ns)
                if ok.any():
                    keep.loc[idx_i] = True
                    keep.loc[a_idx[ok]] = True

            # 自分を end 昇順で挿入
            pos = np.searchsorted(a_e, ei)
            a_idx = np.insert(a_idx, pos, idx_i)
            a_s   = np.insert(a_s,   pos, si)
            a_e   = np.insert(a_e,   pos, ei)
            a_u   = np.insert(a_u,   pos, ui)

    # フィルタ結果（全カラム保持、要求どおりのソートで返す）
    return x[keep].sort_values([bname_col, s_col], kind="mergesort")
# ===== 実行例 =====
df = pd.read_parquet(
    "/Volumes/一ノ瀬/タッカー分解/ファイル/東広島滞在データwith_building.parquet"
)

filtered = keep_overlaps_5min_fast_allcols(df)

# Parquetで保存（全カラム保持）
filtered.to_parquet(
    "/Volumes/一ノ瀬/タッカー分解/ファイル/東広島共滞在データwith_building.parquet",
    index=False,
)
