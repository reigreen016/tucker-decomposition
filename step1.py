# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence, List
import numpy as np
import pandas as pd
from tqdm import tqdm
import pyarrow as pa
import pyarrow.parquet as pq
import matplotlib.pyplot as plt
import matplotlib as mpl


# ============================================================
# 0. matplotlib 日本語設定
# ============================================================
mpl.rcParams["font.family"] = "Hiragino Sans"
mpl.rcParams["axes.unicode_minus"] = False


# ============================================================
# 1. 共通ユーティリティ
# ============================================================
def is_hidden_like(p: Path) -> bool:
    return p.name.startswith("._") or p.name.startswith(".")


def iter_parquet_files(dir_path: Path, glob_pattern: str = "*.parquet") -> list[Path]:
    files = sorted(dir_path.glob(glob_pattern))
    return [
        p for p in files
        if p.is_file()
        and (not is_hidden_like(p))
        and p.stat().st_size > 0
    ]


def safe_write_parquet(
    df: pd.DataFrame | pa.Table,
    out_fp: Path,
    compression: str = "snappy",
) -> None:
    out_fp.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_fp.with_suffix(out_fp.suffix + ".tmp")

    if isinstance(df, pd.DataFrame):
        table = pa.Table.from_pandas(df, preserve_index=False)
    else:
        table = df

    pq.write_table(
        table,
        tmp,
        compression=compression,
        use_dictionary=True,
        write_statistics=False,
    )
    tmp.replace(out_fp)


# ============================================================
# 2. 生データ読込
# ============================================================
def read_trip_file(fp: str | Path) -> pd.DataFrame:
    return pq.read_table(fp).to_pandas()


# ============================================================
# 3. datetime変換
# ============================================================
def convert_time_columns(
    df: pd.DataFrame,
    start_col: str = "Time_start",
    end_col: str = "Time_end",
) -> pd.DataFrame:
    x = df.copy()

    if start_col in x.columns:
        x[start_col] = pd.to_datetime(x[start_col], errors="coerce")

    if end_col in x.columns:
        x[end_col] = pd.to_datetime(x[end_col], errors="coerce")

    return x


# ============================================================
# 4. ソート
# ============================================================
def sort_by_user_time(
    df: pd.DataFrame,
    user_col: str = "User_Id",
    start_col: str = "Time_start",
    end_col: str = "Time_end",
) -> pd.DataFrame:
    x = df.copy()
    keys = [c for c in [user_col, start_col, end_col] if c in x.columns]

    if keys:
        x = x.sort_values(
            keys,
            ascending=True,
            kind="mergesort",
        ).reset_index(drop=True)

    return x


# ============================================================
# 5. 破損行除外
# ============================================================
def drop_invalid_rows(
    df: pd.DataFrame,
    start_col: str = "Time_start",
    end_col: str = "Time_end",
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    x = df.copy()

    invalid_mask = (
        x[start_col].isna()
        | x[end_col].isna()
        | (x[end_col] < x[start_col])
    )

    removed = x.loc[invalid_mask].copy()
    kept = x.loc[~invalid_mask].copy().reset_index(drop=True)

    stats = {
        "input_rows": int(len(x)),
        "removed_invalid_rows": int(len(removed)),
        "output_rows": int(len(kept)),
    }

    return kept, removed, stats


# ============================================================
# 6. 完全重複削除
# ============================================================
def drop_exact_duplicates(
    df: pd.DataFrame,
    subset: Optional[Sequence[str]] = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    x = df.copy()

    if subset is None:
        subset = [c for c in ["User_Id", "Time_start", "Time_end"] if c in x.columns]

    if not subset:
        removed = x.iloc[0:0].copy()

        stats = {
            "input_rows": int(len(x)),
            "removed_exact_duplicates": 0,
            "output_rows": int(len(x)),
        }

        return x.reset_index(drop=True), removed, stats

    dup_mask = x.duplicated(subset=subset, keep="first")

    removed = x.loc[dup_mask].copy()
    kept = x.loc[~dup_mask].copy().reset_index(drop=True)

    stats = {
        "input_rows": int(len(x)),
        "removed_exact_duplicates": int(len(removed)),
        "output_rows": int(len(kept)),
    }

    return kept, removed, stats


# ============================================================
# 7. 時間重複削除（cummaxルール）【修正版】
# ============================================================
def drop_time_overlaps_cummax(
    df: pd.DataFrame,
    user_col: str = "User_Id",
    start_col: str = "Time_start",
    end_col: str = "Time_end",
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    x = df.copy()

    x = x.sort_values(
        [user_col, start_col, end_col],
        ascending=True,
        kind="mergesort",
    ).reset_index(drop=True)

    cummax_end = x.groupby(user_col, sort=False)[end_col].cummax()

    # ユーザーごとに shift する
    prev_cummax_end = cummax_end.groupby(x[user_col], sort=False).shift(1)

    overlap_mask = prev_cummax_end.notna() & (x[start_col] < prev_cummax_end)

    removed = x.loc[overlap_mask].copy()
    kept = x.loc[~overlap_mask].copy().reset_index(drop=True)

    stats = {
        "input_rows": int(len(x)),
        "removed_time_overlaps": int(len(removed)),
        "output_rows": int(len(kept)),
    }

    return kept, removed, stats


# ============================================================
# 8. +9h 補正
# ============================================================
def shift_time_columns(
    df: pd.DataFrame,
    cols: Sequence[str] = ("Time_start", "Time_end"),
    hours: int = 9,
) -> pd.DataFrame:
    x = df.copy()
    delta = pd.Timedelta(hours=hours)

    for c in cols:
        if c in x.columns:
            x[c] = pd.to_datetime(x[c], errors="coerce") + delta

    return x


# ============================================================
# 9. 日跨ぎトリップ分割【高速版】
# ============================================================
def split_trips_by_day_end(
    df: pd.DataFrame,
    start_col: str = "Time_start",
    end_col: str = "Time_end",
) -> tuple[pd.DataFrame, dict]:
    x = df.copy()

    x[start_col] = pd.to_datetime(x[start_col], errors="coerce")
    x[end_col] = pd.to_datetime(x[end_col], errors="coerce")

    valid = (
        x[start_col].notna()
        & x[end_col].notna()
        & (x[end_col] >= x[start_col])
    )

    x = x.loc[valid].copy().reset_index(drop=True)

    if len(x) == 0:
        stats = {
            "input_rows": int(len(df)),
            "split_increment": 0,
            "output_rows": 0,
        }
        return x, stats

    start_day = x[start_col].dt.normalize()
    end_day = x[end_col].dt.normalize()

    n_parts = (end_day - start_day).dt.days + 1

    if int(n_parts.max()) == 1:
        stats = {
            "input_rows": int(len(df)),
            "split_increment": 0,
            "output_rows": int(len(x)),
        }
        return x.reset_index(drop=True), stats

    repeated_index = np.repeat(
        np.arange(len(x)),
        n_parts.to_numpy(dtype=np.int64),
    )

    out = x.iloc[repeated_index].copy().reset_index(drop=True)

    part_no = (
        pd.Series(repeated_index)
        .groupby(repeated_index)
        .cumcount()
        .to_numpy()
    )

    n_parts_rep = n_parts.iloc[repeated_index].to_numpy()

    orig_start = x[start_col].iloc[repeated_index].reset_index(drop=True)
    orig_end = x[end_col].iloc[repeated_index].reset_index(drop=True)
    orig_start_day = start_day.iloc[repeated_index].reset_index(drop=True)

    part_start_day = orig_start_day + pd.to_timedelta(part_no, unit="D")

    one_us = pd.Timedelta(microseconds=1)

    # 分割後の開始時刻
    # 1つ目は元の Time_start、それ以外は当日 00:00
    new_start = part_start_day.copy()
    first_mask = part_no == 0
    new_start.loc[first_mask] = orig_start.loc[first_mask]

    # 分割後の終了時刻
    # 最後は元の Time_end、それ以外は当日 23:59:59.999999
    new_end = part_start_day + pd.Timedelta(days=1) - one_us
    last_mask = part_no == (n_parts_rep - 1)
    new_end.loc[last_mask] = orig_end.loc[last_mask]

    out[start_col] = new_start.to_numpy()
    out[end_col] = new_end.to_numpy()

    # 0秒以下の行は除外
    out = out.loc[out[end_col] > out[start_col]].copy().reset_index(drop=True)

    stats = {
        "input_rows": int(len(df)),
        "split_increment": int(len(out) - len(x)),
        "output_rows": int(len(out)),
    }

    return out, stats


# ============================================================
# 10. ギャップ圧縮【高速版】
#
# 同一ユーザー内で時系列順に並べたうえで、
# 2本目以降の Time_start を直前トリップの Time_end に置き換える。
#
# Time_end は変更しない。
# そのため、トリップ間の空白時間は後続トリップに吸収される。
# ============================================================
def compress_gaps_per_user(
    df: pd.DataFrame,
    user_col: str = "User_Id",
    start_col: str = "Time_start",
    end_col: str = "Time_end",
) -> pd.DataFrame:
    x = df.copy()

    x = x.sort_values(
        [user_col, start_col, end_col],
        ascending=True,
        kind="mergesort",
    ).reset_index(drop=True)

    x[start_col] = pd.to_datetime(x[start_col], errors="coerce")
    x[end_col] = pd.to_datetime(x[end_col], errors="coerce")

    # 同一ユーザー内の直前トリップ終了時刻
    prev_end = x.groupby(user_col, sort=False)[end_col].shift(1)

    # 2本目以降の Time_start を直前 Time_end に置換
    mask = prev_end.notna()
    x.loc[mask, start_col] = prev_end.loc[mask]

    return x.reset_index(drop=True)


# ============================================================
# 11. 日付キー付与
# ============================================================
def add_date_key(
    df: pd.DataFrame,
    start_col: str = "Time_start",
    date_col: str = "__date__",
) -> pd.DataFrame:
    x = df.copy()
    x[date_col] = pd.to_datetime(x[start_col], errors="coerce").dt.strftime("%Y%m%d")

    return x


# ============================================================
# 12. 日別パーツ保存
# ============================================================
def write_daily_parts(
    df: pd.DataFrame,
    parts_dir: Path,
    source_stem: str,
    compression: str = "snappy",
    date_col: str = "__date__",
) -> None:
    x = df.copy()

    for date, g in x.groupby(date_col, sort=False):
        out_dir = parts_dir / f"date={date}"
        out_fp = out_dir / f"{source_stem}__{date}.parquet"

        safe_write_parquet(
            g.drop(columns=[date_col]),
            out_fp,
            compression=compression,
        )


# ============================================================
# 13. parts から日別最終出力を作る
#
# ここは前回の修正版のまま。
# 日別パーツを結合した後に、
# 完全重複と時間重複を再度確認・削除する。
# ============================================================
def consolidate_daily_from_parts(
    parts_dir: Path,
    out_dir: Path,
    compression: str = "snappy",
    user_col: str = "User_Id",
    start_col: str = "Time_start",
    end_col: str = "Time_end",
    dedup_subset: Optional[Sequence[str]] = None,
) -> None:
    date_dirs = sorted([p for p in parts_dir.glob("date=*") if p.is_dir()])

    for ddir in tqdm(date_dirs, desc="StepB: 日別結合"):
        date = ddir.name.split("=", 1)[1]

        part_files = sorted(
            [
                p for p in ddir.glob("*.parquet")
                if p.is_file()
                and (not is_hidden_like(p))
                and p.stat().st_size > 0
            ]
        )

        if not part_files:
            continue

        chunks = []

        for p in part_files:
            chunks.append(pd.read_parquet(p))

        if not chunks:
            continue

        day_df = pd.concat(chunks, ignore_index=True)

        # datetime変換
        day_df = convert_time_columns(day_df, start_col, end_col)

        # ソート
        day_df = sort_by_user_time(day_df, user_col, start_col, end_col)

        # 完全重複削除
        if dedup_subset is None:
            dedup_subset = [user_col, start_col, end_col]

        day_df, removed_exact_final, st_exact_final = drop_exact_duplicates(
            day_df,
            subset=dedup_subset,
        )

        # 時間重複削除
        day_df = sort_by_user_time(day_df, user_col, start_col, end_col)

        day_df, removed_overlap_final, st_overlap_final = drop_time_overlaps_cummax(
            day_df,
            user_col=user_col,
            start_col=start_col,
            end_col=end_col,
        )

        # Time_start が対象日付の行だけ残す
        # 日別ファイルは Time_start 基準で作成する
        day_df = convert_time_columns(day_df, start_col, end_col)
        start_date = day_df[start_col].dt.strftime("%Y%m%d")
        day_df = day_df.loc[start_date == date].copy()

        # 最終ソート
        day_df = sort_by_user_time(day_df, user_col, start_col, end_col)

        out_fp = out_dir / f"trips_{date}.parquet"

        safe_write_parquet(
            day_df,
            out_fp,
            compression=compression,
        )

        print(
            f"[{date}] "
            f"final_rows={len(day_df)}, "
            f"removed_exact={st_exact_final['removed_exact_duplicates']}, "
            f"removed_overlap={st_overlap_final['removed_time_overlaps']}"
        )


# ============================================================
# 14. トリップ時間の分布図作成
#
# ここはそのまま。
# ============================================================
def plot_trip_duration_distribution_from_parquets_jp(
    parquet_dir: str | Path,
    out_dir: str | Path,
    file_pattern: str = "trips_*.parquet",
    start_col: str = "Time_start",
    end_col: str = "Time_end",
    max_hours: float = 24,
    bins: int = 100,
) -> None:
    parquet_dir = Path(parquet_dir)
    out_dir = Path(out_dir)

    out_dir.mkdir(parents=True, exist_ok=True)

    files = iter_parquet_files(parquet_dir, file_pattern)

    if not files:
        print("[WARN] parquet が見つかりません。")
        return

    hour_edges = np.linspace(0, max_hours, bins + 1)
    min_edges = np.linspace(0, max_hours * 60, bins + 1)

    hour_counts = np.zeros(bins, dtype=np.int64)
    min_counts = np.zeros(bins, dtype=np.int64)

    total_count = 0
    total_sum_min = 0.0
    total_sum_hour = 0.0
    max_min = 0.0
    max_hour = 0.0

    duration_min_parts = []
    duration_hour_parts = []

    for fp in tqdm(files, desc="Step16: 分布図用parquet読込"):
        df = pd.read_parquet(fp, columns=[start_col, end_col])

        df[start_col] = pd.to_datetime(df[start_col], errors="coerce")
        df[end_col] = pd.to_datetime(df[end_col], errors="coerce")

        duration_sec = (df[end_col] - df[start_col]).dt.total_seconds()
        duration_sec = duration_sec[(duration_sec.notna()) & (duration_sec > 0)]

        if len(duration_sec) == 0:
            continue

        duration_hour = (duration_sec / 3600.0).to_numpy()
        duration_min = (duration_sec / 60.0).to_numpy()

        total_count += len(duration_sec)
        total_sum_min += duration_min.sum()
        total_sum_hour += duration_hour.sum()

        max_min = max(max_min, float(duration_min.max()))
        max_hour = max(max_hour, float(duration_hour.max()))

        duration_min_parts.append(duration_min)
        duration_hour_parts.append(duration_hour)

        duration_hour_clip = duration_hour[duration_hour <= max_hours]
        duration_min_clip = duration_min[duration_min <= max_hours * 60]

        h_counts, _ = np.histogram(duration_hour_clip, bins=hour_edges)
        m_counts, _ = np.histogram(duration_min_clip, bins=min_edges)

        hour_counts += h_counts
        min_counts += m_counts

    if total_count == 0:
        print("[WARN] 有効なトリップ時間データがありません。")
        return

    all_duration_min = np.concatenate(duration_min_parts)
    all_duration_hour = np.concatenate(duration_hour_parts)

    # 時間単位ヒストグラム
    plt.figure(figsize=(10, 6))
    plt.bar(hour_edges[:-1], hour_counts, width=np.diff(hour_edges), align="edge")
    plt.xlabel("トリップ時間（時間）")
    plt.ylabel("件数")
    plt.title("トリップ時間分布（時間）")
    plt.tight_layout()

    out_fp_hour = out_dir / "トリップ時間分布_時間.png"
    plt.savefig(out_fp_hour, dpi=200, bbox_inches="tight")
    plt.close()

    # 分単位ヒストグラム
    plt.figure(figsize=(10, 6))
    plt.bar(min_edges[:-1], min_counts, width=np.diff(min_edges), align="edge")
    plt.xlabel("トリップ時間（分）")
    plt.ylabel("件数")
    plt.title("トリップ時間分布（分）")
    plt.tight_layout()

    out_fp_min = out_dir / "トリップ時間分布_分.png"
    plt.savefig(out_fp_min, dpi=200, bbox_inches="tight")
    plt.close()

    summary = pd.DataFrame({
        "項目": [
            "件数",
            "平均（分）",
            "中央値（分）",
            "90パーセンタイル（分）",
            "95パーセンタイル（分）",
            "99パーセンタイル（分）",
            "最大値（分）",
            "平均（時間）",
            "中央値（時間）",
            "90パーセンタイル（時間）",
            "95パーセンタイル（時間）",
            "99パーセンタイル（時間）",
            "最大値（時間）",
            "描画上限（時間）",
            "ビン数",
        ],
        "値": [
            total_count,
            total_sum_min / total_count,
            float(np.median(all_duration_min)),
            float(np.quantile(all_duration_min, 0.90)),
            float(np.quantile(all_duration_min, 0.95)),
            float(np.quantile(all_duration_min, 0.99)),
            max_min,
            total_sum_hour / total_count,
            float(np.median(all_duration_hour)),
            float(np.quantile(all_duration_hour, 0.90)),
            float(np.quantile(all_duration_hour, 0.95)),
            float(np.quantile(all_duration_hour, 0.99)),
            max_hour,
            max_hours,
            bins,
        ],
    })

    summary_fp = out_dir / "トリップ時間分布_要約統計.csv"
    summary.to_csv(summary_fp, index=False, encoding="utf-8-sig")

    print(f"[OUTPUT] 時間分布図 : {out_fp_hour}")
    print(f"[OUTPUT] 分分布図   : {out_fp_min}")
    print(f"[OUTPUT] 要約統計   : {summary_fp}")


# ============================================================
# 15. 複数ファイル一括処理
# ============================================================
def run_pipeline(
    in_dir: str | Path,
    out_dir: str | Path,
    parts_dir: str | Path,
    plot_dir: str | Path,
    glob_pattern: str = "trips_*.parquet",
    user_col: str = "User_Id",
    start_col: str = "Time_start",
    end_col: str = "Time_end",
    tz_shift_hours: int = 9,
    dedup_subset: Optional[Sequence[str]] = None,
    compression: str = "snappy",
) -> None:
    in_dir = Path(in_dir)
    out_dir = Path(out_dir)
    parts_dir = Path(parts_dir)
    plot_dir = Path(plot_dir)

    out_dir.mkdir(parents=True, exist_ok=True)
    parts_dir.mkdir(parents=True, exist_ok=True)
    plot_dir.mkdir(parents=True, exist_ok=True)

    files = iter_parquet_files(in_dir, glob_pattern)

    if not files:
        raise FileNotFoundError(f"No parquet files matched: {in_dir}/{glob_pattern}")

    stats_rows: List[dict] = []

    for fp in tqdm(files, desc="StepA: ファイル処理"):
        file_stats: dict = {"入力ファイル名": fp.name}

        # Step1: 読込
        df = read_trip_file(fp)
        file_stats["入力行数"] = int(len(df))

        # Step2: datetime変換
        x = convert_time_columns(df, start_col, end_col)

        # Step3: ソート
        x = sort_by_user_time(x, user_col, start_col, end_col)

        # Step4: 破損行除外（1回目）
        x, removed_invalid_1, st_invalid_1 = drop_invalid_rows(
            x,
            start_col,
            end_col,
        )
        file_stats["破損行削除数_1回目"] = st_invalid_1["removed_invalid_rows"]

        # Step5: 完全重複削除
        x, removed_exact, st_exact = drop_exact_duplicates(
            x,
            subset=dedup_subset,
        )
        file_stats["完全重複削除数"] = st_exact["removed_exact_duplicates"]

        # Step6: 時間重複削除
        x = sort_by_user_time(x, user_col, start_col, end_col)

        x, removed_overlap, st_overlap = drop_time_overlaps_cummax(
            x,
            user_col,
            start_col,
            end_col,
        )
        file_stats["時間重複削除数"] = st_overlap["removed_time_overlaps"]

        # Step7: +9h
        x = shift_time_columns(
            x,
            [start_col, end_col],
            tz_shift_hours,
        )

        # Step8: 再ソート
        x = sort_by_user_time(x, user_col, start_col, end_col)

        # Step9: ギャップ圧縮【高速版】
        # 2本目以降の Time_start を直前トリップの Time_end に置き換える。
        # Time_end は変更しない。
        x = compress_gaps_per_user(
            x,
            user_col,
            start_col,
            end_col,
        )

        # Step10: ギャップ圧縮後の破損チェック
        x = convert_time_columns(x, start_col, end_col)

        x, removed_invalid_2, st_invalid_2 = drop_invalid_rows(
            x,
            start_col,
            end_col,
        )
        file_stats["破損行削除数_2回目"] = st_invalid_2["removed_invalid_rows"]

        # Step11: ギャップ圧縮後に日跨ぎ分割【高速版】
        # Time_start を前に動かしたことで発生した日跨ぎをここで分割する。
        x, st_split = split_trips_by_day_end(
            x,
            start_col,
            end_col,
        )
        file_stats["日跨ぎ分割増分"] = st_split["split_increment"]

        # Step12: 分割後に再ソート
        x = sort_by_user_time(x, user_col, start_col, end_col)

        # Step13: 分割後の破損チェック
        x = convert_time_columns(x, start_col, end_col)

        x, removed_invalid_3, st_invalid_3 = drop_invalid_rows(
            x,
            start_col,
            end_col,
        )
        file_stats["破損行削除数_3回目"] = st_invalid_3["removed_invalid_rows"]

        # Step14: 日付キー付与
        x = add_date_key(x, start_col, "__date__")

        # Step15: 日別パーツ保存
        write_daily_parts(
            x,
            parts_dir=parts_dir,
            source_stem=fp.stem,
            compression=compression,
            date_col="__date__",
        )

        file_stats["最終行数"] = int(len(x))
        stats_rows.append(file_stats)

    # Step16: 日別に結合して最終出力
    consolidate_daily_from_parts(
        parts_dir=parts_dir,
        out_dir=out_dir,
        compression=compression,
        user_col=user_col,
        start_col=start_col,
        end_col=end_col,
        dedup_subset=dedup_subset,
    )

    # Step17: 統計CSV
    stats_df = pd.DataFrame(stats_rows)

    stats_csv = out_dir / "処理統計_入力ファイル別.csv"
    stats_df.to_csv(stats_csv, index=False, encoding="utf-8-sig")

    # Step18: 最終出力からトリップ時間分布図を作成
    # ここは一旦そのまま残す
    plot_trip_duration_distribution_from_parquets_jp(
        parquet_dir=out_dir,
        out_dir=plot_dir,
        file_pattern="trips_*.parquet",
        start_col=start_col,
        end_col=end_col,
        max_hours=24,
        bins=100,
    )

    print(f"[OUTPUT] 最終出力      : {out_dir}")
    print(f"[OUTPUT] 中間パーツ    : {parts_dir}")
    print(f"[OUTPUT] 図表出力      : {plot_dir}")
    print(f"[OUTPUT] 処理統計CSV   : {stats_csv}")


# ============================================================
# 16. 実行例
# ============================================================
if __name__ == "__main__":
    IN_DIR = (
        "/Volumes/一ノ瀬/09_共滞在アルバイト/"
        "01_【第1層】下処理（Preprocessing）コードの整理/"
        "02_trial/入力"
    )

    OUT_DIR = (
        "/Volumes/一ノ瀬/09_共滞在アルバイト/"
        "01_【第1層】下処理（Preprocessing）コードの整理/"
        "02_trial/出力_20260604_fast/step2_daily"
    )

    PARTS_DIR = (
        "/Volumes/一ノ瀬/09_共滞在アルバイト/"
        "01_【第1層】下処理（Preprocessing）コードの整理/"
        "02_trial/出力_20260604_fast/_daily_parts"
    )

    PLOT_DIR = (
        "/Volumes/一ノ瀬/09_共滞在アルバイト/"
        "01_【第1層】下処理（Preprocessing）コードの整理/"
        "02_trial/出力_20260604_fast/plots"
    )

    DEDUP_SUBSET = ["User_Id", "Time_start", "Time_end"]

    run_pipeline(
        in_dir=IN_DIR,
        out_dir=OUT_DIR,
        parts_dir=PARTS_DIR,
        plot_dir=PLOT_DIR,
        glob_pattern="trips_*.parquet",
        user_col="User_Id",
        start_col="Time_start",
        end_col="Time_end",
        tz_shift_hours=9,
        dedup_subset=DEDUP_SUBSET,
        compression="snappy",
    )
