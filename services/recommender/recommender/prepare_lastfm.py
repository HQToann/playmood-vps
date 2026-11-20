import argparse
from collections import Counter
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd

from .config import (
    MAX_SONGS,
    MAX_USERS,
    PROCESSED_DATA_DIR,
    PROCESSED_INTERACTIONS_FILE,
    PROCESSED_SONGS_FILE,
    RAW_DATA_DIR,
)
from .data_prep import clean_and_aggregate, filter_subset

DEFAULT_RAW_FILE = RAW_DATA_DIR / "userid-timestamp-artid-artname-traid-traname.tsv"


def iter_lastfm_rows(raw_path: Path, max_lines: Optional[int] = None):
    """Đọc từng dòng tệp TSV Last.fm-1K để tiết kiệm RAM và tránh lỗi dấu ngoặc kép."""
    with raw_path.open("r", encoding="utf-8", errors="ignore") as f:
        for line_idx, line in enumerate(f, start=1):
            if max_lines is not None and line_idx > max_lines:
                break

            parts = line.rstrip("\r\n").split("\t")
            if len(parts) < 6:
                continue

            user_id = parts[0].strip()
            artist = parts[3].strip()
            title = parts[5].strip()

            # Bỏ qua dòng thiếu thông tin hoặc dòng tiêu đề (nếu bản tải về có header)
            if not user_id or not artist or not title:
                continue
            if user_id.lower() in {"userid", "user_id"}:
                continue

            track_key = (artist.lower(), title.lower())
            yield user_id, track_key, artist, title


def prepare_lastfm_dataset(
    raw_path: Path = DEFAULT_RAW_FILE,
    max_users: int = MAX_USERS,
    max_songs: int = MAX_SONGS,
    max_lines: Optional[int] = None,
) -> None:
    """Chuyển dữ liệu thô Last.fm-1K thành interactions.csv và songs.csv chuẩn."""
    if not raw_path.exists():
        raise FileNotFoundError(
            f"Không tìm thấy tệp dữ liệu thô tại: {raw_path}\n"
            f"Hãy đặt tệp 'userid-timestamp-artid-artname-traid-traname.tsv' vào thư mục data/raw/."
        )

    print(f"[1/3] Đang quét lượt 1 để tìm Top {max_songs} bài hát phổ biến nhất...")
    track_counts: Counter = Counter()
    track_display: Dict[Tuple[str, str], Tuple[str, str]] = {}
    valid_events = 0

    for _, track_key, artist, title in iter_lastfm_rows(raw_path, max_lines=max_lines):
        track_counts[track_key] += 1
        if track_key not in track_display:
            track_display[track_key] = (title, artist)
        valid_events += 1

        if valid_events % 2_000_000 == 0:
            print(f"      Đã đọc {valid_events:,} lượt nghe hợp lệ...")

    if valid_events == 0:
        raise ValueError("Không đọc được bản ghi hợp lệ nào từ tệp đầu vào.")

    top_tracks = track_counts.most_common(max_songs)
    track_to_song_id = {
        track_key: f"S{idx:04d}"
        for idx, (track_key, _) in enumerate(top_tracks, start=1)
    }

    print(
        f"      Hoàn tất lượt 1: {valid_events:,} lượt nghe, "
        f"{len(track_counts):,} bài duy nhất -> chọn Top {len(track_to_song_id)} bài."
    )

    print("[2/3] Đang quét lượt 2 để tổng hợp lượt nghe theo từng cặp (user_id, song_id)...")
    pair_counts: Counter = Counter()
    for user_id, track_key, _, _ in iter_lastfm_rows(raw_path, max_lines=max_lines):
        song_id = track_to_song_id.get(track_key)
        if song_id is not None:
            pair_counts[(user_id, song_id)] += 1

    if not pair_counts:
        raise ValueError("Không có tương tác nào khớp với danh sách bài hát đã chọn.")

    raw_interactions_df = pd.DataFrame(
        [
            {"user_id": u, "song_id": s, "listen_count": c}
            for (u, s), c in pair_counts.items()
        ]
    )

    print(f"[3/3] Làm sạch và cắt tập con ({max_users} hồ sơ x tối đa {max_songs} bài hát)...")
    agg_df = clean_and_aggregate(raw_interactions_df)
    subset_df = filter_subset(agg_df, max_users=max_users, max_songs=max_songs)

    kept_song_ids = set(subset_df["song_id"].unique())
    songs_rows = []
    for track_key, song_id in track_to_song_id.items():
        if song_id in kept_song_ids:
            title, artist = track_display[track_key]
            songs_rows.append({"song_id": song_id, "title": title, "artist": artist})
    songs_df = pd.DataFrame(songs_rows).sort_values("song_id").reset_index(drop=True)

    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    subset_df.to_csv(PROCESSED_INTERACTIONS_FILE, index=False)
    songs_df.to_csv(PROCESSED_SONGS_FILE, index=False)

    num_users = subset_df["user_id"].nunique()
    num_songs = subset_df["song_id"].nunique()
    num_pairs = len(subset_df)
    total_listens = int(subset_df["listen_count"].sum())
    density = (num_pairs / (num_users * num_songs)) * 100 if num_users and num_songs else 0.0

    print("\n--- THONG KE TAP DU LIEU LAST.FM-1K DA CHUAN BI ---")
    print(f"File interactions : {PROCESSED_INTERACTIONS_FILE}")
    print(f"File songs        : {PROCESSED_SONGS_FILE}")
    print(f"So ho so (users)  : {num_users}")
    print(f"So bai hat (songs): {num_songs}")
    print(f"So cap tuong tac  : {num_pairs:,}")
    print(f"Tong so luot nghe : {total_listens:,}")
    print(f"Do day ma tran    : {density:.2f}%")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tiền xử lý tập dữ liệu Last.fm-1K.")
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_RAW_FILE,
        help="Đường dẫn tới tệp TSV thô của Last.fm-1K.",
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        default=None,
        help="Giới hạn số dòng đọc thử (bỏ trống để đọc toàn bộ tệp).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    prepare_lastfm_dataset(
        raw_path=args.input,
        max_users=MAX_USERS,
        max_songs=MAX_SONGS,
        max_lines=args.max_lines,
    )