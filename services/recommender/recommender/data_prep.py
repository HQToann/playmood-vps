from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor

from .config import (
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_USER,
    MAX_SONGS,
    MAX_USERS,
    PROCESSED_INTERACTIONS_FILE,
    PROCESSED_SONGS_FILE
)


@dataclass
class InteractionDataset:
    """cấu trúc dữ liệu chuẩn
    - matrix: ma trận 2 chiều (số_user x số_bài_hát) mỗi ô chứa tổng số lượt nghe
    - user_to_idx / idx_to_user: Ánh xạ giữa mã người dùng thật và chỉ số hàng trong ma trận.
    - song_to_idx / idx_to_song: Ánh xạ giữa mã bài hát thật và chỉ số cột trong ma trận.
    - song_metadata: Lưu tên bài hát và tên nghệ sĩ để hiển thị lên website.
    """

    matrix: np.ndarray
    user_to_idx: Dict[str, int]
    idx_to_user: List[str]
    song_to_idx: Dict[str, int]
    idx_to_song: List[str]
    song_metadata: Dict[str, Dict[str, str]] = field(default_factory=dict)

    @property
    def num_users(self) -> int:
        return len(self.idx_to_user)

    @property
    def num_songs(self) -> int:
        return len(self.idx_to_song)


def get_db_connection():
    #tạo kết nối đến postgre trên máy vm3
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )


def clean_and_aggregate(raw_df: pd.DataFrame) -> pd.DataFrame:
    """làm sạch dữ liệu nghe và cộng dồn lượt nghe theo đúng 1 chuẩn đầu vào duy nhất:
    3 cột (user_id, song_id, listen_count)."""

    required_cols = {"user_id", "song_id", "listen_count"}
    if not required_cols.issubset(raw_df.columns):
        raise ValueError(f"Dữ liệu đầu vào phải có đủ 3 cột chuẩn: {required_cols}")

    # 1. loại bỏ dòng bị thiếu dữ liệu ở 3 cột bắt buộc
    df = raw_df[["user_id", "song_id", "listen_count"]].dropna().copy()
    df["user_id"] = df["user_id"].astype(str).str.strip()
    df["song_id"] = df["song_id"].astype(str).str.strip()
    df["listen_count"] = pd.to_numeric(df["listen_count"], errors="coerce").fillna(0)

    #2. giữ lại các bản ghi có mã hợp lệ và số lượt nghe > 0
    df = df[(df["user_id"] != "") & (df["song_id"] != "") & (df["listen_count"] > 0)]

    #3. cộng dồn số lượt nghe theo từng cặp (user_id, song_id)
    return (
        df.groupby(["user_id", "song_id"], as_index=False)["listen_count"]
        .sum()
        .reset_index(drop=True)
    )


def filter_subset(
    agg_df: pd.DataFrame,
    max_users: int = MAX_USERS,
    max_songs: int = MAX_SONGS,
) -> pd.DataFrame:
    #1. lấy bài hát có tổng lượt nghe cao nhất
    top_songs = (
        agg_df.groupby("song_id")["listen_count"]
        .sum()
        .nlargest(max_songs)
        .index
    )

    df = agg_df[agg_df["song_id"].isin(top_songs)]

    #2. lấy top hồ sơ nghe nhiều bài hát khác nhau nhất (để đủ dữ liệu chia train/test)
    top_users = (
        df.groupby("user_id")["song_id"]
        .nunique()
        .nlargest(max_users)
        .index
    )
    return df[df["user_id"].isin(top_users)].reset_index(drop=True)


def build_interaction_matrix(
    interactions_df: pd.DataFrame,
    songs_df: Optional[pd.DataFrame] = None,
) -> InteractionDataset:
    """chuyển DataFrame (user_id, song_id, listen_count) thành ma trận NumPy 2 chiều.
    Mỗi hàng là 1 người dùng, mỗi cột là 1 bài hát, giá trị là số lượt nghe.
    """
    if interactions_df.empty:
        return InteractionDataset(
            matrix=np.zeros((0, 0), dtype=np.float64),
            user_to_idx={},
            idx_to_user=[],
            song_to_idx={},
            idx_to_song=[],
            song_metadata={},
        )

    # Tạo bảng ánh xạ ID thật <-> chỉ số hàng/cột (0, 1, 2, ...)
    idx_to_user = sorted(interactions_df["user_id"].astype(str).unique().tolist())
    idx_to_song = sorted(interactions_df["song_id"].astype(str).unique().tolist())

    user_to_idx = {uid: i for i, uid in enumerate(idx_to_user)}
    song_to_idx = {sid: j for j, sid in enumerate(idx_to_song)}

    # Điền tổng số lượt nghe vào ma trận 2 chiều
    matrix = np.zeros((len(idx_to_user), len(idx_to_song)), dtype=np.float64)
    for row in interactions_df.itertuples(index=False):
        u_idx = user_to_idx[str(row.user_id)]
        s_idx = song_to_idx[str(row.song_id)]
        matrix[u_idx, s_idx] = float(row.listen_count)

    # Nạp thêm thông tin tên bài hát và nghệ sĩ (nếu có)
    song_metadata: Dict[str, Dict[str, str]] = {}
    if songs_df is not None and not songs_df.empty:
        for row in songs_df.itertuples(index=False):
            sid = str(row.song_id)
            song_metadata[sid] = {
                "title": str(getattr(row, "title", sid)),
                "artist": str(getattr(row, "artist", "Unknown Artist")),
            }

    return InteractionDataset(
        matrix=matrix,
        user_to_idx=user_to_idx,
        idx_to_user=idx_to_user,
        song_to_idx=song_to_idx,
        idx_to_song=idx_to_song,
        song_metadata=song_metadata,
    )


def load_from_csv(
    interactions_path: Path = PROCESSED_INTERACTIONS_FILE,
    songs_path: Optional[Path] = PROCESSED_SONGS_FILE,
    apply_limits: bool = False,
) -> InteractionDataset:
    """đọc tập dữ liệu đã làm sạch từ file CSV (dùng cho bước đánh giá Recall offline).
    """
    raw_df = pd.read_csv(interactions_path)
    interactions_df = clean_and_aggregate(raw_df)

    # Nếu cần cắt gọn về 100 user / 500 bài hát thử nghiệm thì bật apply_limits=True
    if apply_limits:
        interactions_df = filter_subset(
            interactions_df,
            max_users=MAX_USERS,
            max_songs=MAX_SONGS,
        )

    songs_df = None
    if songs_path is not None and Path(songs_path).exists():
        songs_df = pd.read_csv(songs_path)

    return build_interaction_matrix(interactions_df, songs_df)


def load_from_postgres(apply_limits: bool = False) -> InteractionDataset:
    """đọc bảng tương tác lượt nghe và thông tin bài hát từ PostgreSQL (VM3).
    Dùng khi chạy worker thực tế trên VM2.
    - apply_limits=False (mặc định): nạp toàn bộ dữ liệu để suy luận chính xác nhất.
    - apply_limits=True: cắt gọn về MAX_USERS / MAX_SONGS (dùng khi test).
    """
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT user_id::text AS user_id,
                       song_id::text AS song_id,
                       listen_count
                FROM recsys_interactions
                WHERE listen_count > 0
                """
            )
            interaction_rows = cur.fetchall()

            cur.execute(
                """
                SELECT s.id::text AS song_id,
                       s.title,
                       COALESCE(u.username, 'Unknown Artist') AS artist
                FROM music_song s
                LEFT JOIN accounts_user u ON s.artist_id = u.id
                """
            )
            song_rows = cur.fetchall()

        interactions_df = pd.DataFrame(interaction_rows)
        songs_df = pd.DataFrame(song_rows) if song_rows else None

        if interactions_df.empty:
            return build_interaction_matrix(interactions_df, songs_df)

        clean_df = clean_and_aggregate(interactions_df)
        if apply_limits:
            clean_df = filter_subset(clean_df, max_users=MAX_USERS, max_songs=MAX_SONGS)
        return build_interaction_matrix(clean_df, songs_df)
    finally:
        if conn:
            conn.close()


def ensure_recsys_tables() -> None:
    """Đảm bảo bảng lưu tương tác nghe nhạc tồn tại trên PostgreSQL (VM3)."""
    create_sql = """
        CREATE TABLE IF NOT EXISTS recsys_interactions (
            user_id VARCHAR(128) NOT NULL,
            song_id VARCHAR(128) NOT NULL,
            listen_count INTEGER NOT NULL DEFAULT 1 CHECK (listen_count > 0),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, song_id)
        );
    """
    with psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(create_sql)


def upsert_listen_event(
    user_id: str,
    song_id: str,
    increment: int = 1,
) -> int:
    """
    Ghi nhận 1 sự kiện nghe nhạc mới vào bảng recsys_interactions trên PostgreSQL (VM3).
    Nếu cặp (user_id, song_id) đã tồn tại thì cộng dồn listen_count; nếu chưa có thì thêm mới.
    Trả về tổng listen_count mới nhất sau khi cập nhật.
    """
    uid = str(user_id).strip()
    sid = str(song_id).strip()
    inc = max(1, int(increment))

    if not uid or not sid:
        raise ValueError("user_id và song_id không được để trống.")

    upsert_sql = """
        INSERT INTO recsys_interactions (user_id, song_id, listen_count, updated_at)
        VALUES (%s, %s, %s, NOW())
        ON CONFLICT (user_id, song_id)
        DO UPDATE SET
            listen_count = recsys_interactions.listen_count + EXCLUDED.listen_count,
            updated_at = NOW()
        RETURNING listen_count;
    """

    with psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(upsert_sql, (uid, sid, inc))
            new_count = cur.fetchone()[0]
            return int(new_count)