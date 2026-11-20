from typing import Dict, List, Optional

import numpy as np

from .config import TOP_K
from .data_prep import InteractionDataset

VALID_MODES = ("play_count", "log_play_count", "user_count")


class PopularityRecommender:
    """
    Mô hình gợi ý theo độ phổ biến (Popularity):
    - Đóng vai trò mốc so sánh (Baseline) khi đánh giá Recall@5.
    - Đóng vai trò phương án dự phòng (Fallback) cho người dùng mới hoặc thiếu dữ liệu.

    Hỗ trợ 3 chế độ tính điểm phổ biến (mode):
    - "user_count" (mặc định): Đếm số người dùng khác nhau đã nghe bài hát.
    - "log_play_count": Tổng ln(1 + listen_count) để giảm ảnh hưởng tài khoản nghe lặp.
    - "play_count": Tổng lượt nghe thô (mốc Version 1).
    """

    def __init__(self, mode: str = "user_count") -> None:
        if mode not in VALID_MODES:
            raise ValueError(f"mode không hợp lệ: '{mode}'. Chỉ hỗ trợ: {VALID_MODES}")

        self.mode = mode
        self.dataset: Optional[InteractionDataset] = None
        self.song_scores: np.ndarray = np.array([], dtype=np.float64)
        self.ranked_song_indices: np.ndarray = np.array([], dtype=np.int64)

    def fit(self, dataset: InteractionDataset) -> "PopularityRecommender":
        """
        Tính điểm phổ biến của từng bài hát trên toàn tập dữ liệu và xếp hạng giảm dần.
        """
        self.dataset = dataset

        if dataset.num_songs == 0:
            self.song_scores = np.array([], dtype=np.float64)
            self.ranked_song_indices = np.array([], dtype=np.int64)
            return self

        if self.mode == "user_count":
            # Đếm số người dùng khác nhau từng nghe bài hát (loại bỏ nhiễu cày lượt nghe)
            self.song_scores = (dataset.matrix > 0).sum(axis=0).astype(np.float64)
        elif self.mode == "log_play_count":
            # Nén logarit từng ô lượt nghe trước khi cộng dồn theo cột
            self.song_scores = np.log1p(dataset.matrix).sum(axis=0)
        else:
            # Tổng lượt nghe thô (cách tính gốc ở Version 1)
            self.song_scores = dataset.matrix.sum(axis=0)

        # Sắp xếp chỉ số bài hát theo điểm phổ biến giảm dần
        self.ranked_song_indices = np.argsort(-self.song_scores, kind="stable")
        return self

    def recommend(
        self,
        user_id: Optional[str] = None,
        top_k: int = TOP_K,
        exclude_listened: bool = True,
    ) -> List[Dict]:
        """
        Trả về danh sách Top K bài hát phổ biến nhất (mặc định loại bỏ bài user đã nghe).
        Nếu user_id là người mới (chưa có trong ma trận), trả về thẳng Top K toàn hệ thống.
        """
        if self.dataset is None or self.dataset.num_songs == 0 or top_k <= 0:
            return []

        listened_mask = np.zeros(self.dataset.num_songs, dtype=bool)
        if exclude_listened and user_id is not None:
            uid = str(user_id)
            if uid in self.dataset.user_to_idx:
                u_idx = self.dataset.user_to_idx[uid]
                listened_mask = self.dataset.matrix[u_idx] > 0

        recommendations: List[Dict] = []
        for s_idx in self.ranked_song_indices:
            if listened_mask[s_idx]:
                continue

            song_id = self.dataset.idx_to_song[int(s_idx)]
            meta = self.dataset.song_metadata.get(song_id, {})

            recommendations.append(
                {
                    "rank": len(recommendations) + 1,
                    "song_id": song_id,
                    "title": meta.get("title", song_id),
                    "artist": meta.get("artist", "Unknown Artist"),
                    "score": float(self.song_scores[s_idx]),
                    "method": f"popularity_{self.mode}",
                }
            )

            if len(recommendations) >= top_k:
                break

        return recommendations