from typing import Dict, List, Optional

import numpy as np

from .config import K_NEIGHBORS, MIN_SIMILARITY, TOP_K
from .data_prep import InteractionDataset
from .popularity import PopularityRecommender


class CosineCFRecommender:
    """
    Mô hình Lọc cộng tác ở mức người dùng (User-based Collaborative Filtering)
    sử dụng độ tương đồng Cosine.
    - Hỗ trợ nén logarit (use_log=True) bằng ln(1 + listen_count) để giảm nhiễu
      từ các tài khoản nghe lặp quá nhiều một vài bài hát.
    - Tự động chuyển sang PopularityRecommender (user_count) nếu người dùng mới
      hoặc không đủ láng giềng.
    """

    def __init__(
        self,
        k_neighbors: int = K_NEIGHBORS,
        min_similarity: float = MIN_SIMILARITY,
        use_log: bool = True,
    ) -> None:
        self.k_neighbors = k_neighbors
        self.min_similarity = min_similarity
        self.use_log = use_log
        self.dataset: Optional[InteractionDataset] = None
        self.weighted_matrix: np.ndarray = np.array([], dtype=np.float64)
        self.similarity_matrix: np.ndarray = np.array([], dtype=np.float64)
        self.fallback_model = PopularityRecommender(mode="user_count")

    def fit(self, dataset: InteractionDataset) -> "CosineCFRecommender":
        """
        Chuẩn hóa trọng số tương tác (thô hoặc log1p), tính trước ma trận
        độ tương đồng Cosine giữa toàn bộ cặp người dùng và huấn luyện fallback.
        """
        self.dataset = dataset
        self.fallback_model.fit(dataset)

        if dataset.num_users == 0 or dataset.num_songs == 0:
            self.weighted_matrix = np.array([], dtype=np.float64)
            self.similarity_matrix = np.array([], dtype=np.float64)
            return self

        # Áp dụng nén logarit ln(1 + x) nếu bật use_log
        if self.use_log:
            working_matrix = np.log1p(dataset.matrix)
        else:
            working_matrix = dataset.matrix.astype(np.float64, copy=False)

        self.weighted_matrix = working_matrix

        # 1. Tính độ dài vector (L2 norm) cho từng hàng (mỗi người dùng)
        norms = np.linalg.norm(working_matrix, axis=1, keepdims=True)
        safe_norms = np.where(norms == 0.0, 1.0, norms)
        normalized_matrix = working_matrix / safe_norms

        # 2. Tích vô hướng của các vector đã chuẩn hóa chính là độ tương đồng Cosine
        sim_matrix = normalized_matrix @ normalized_matrix.T

        # 3. Đặt đường chéo chính bằng 0 để người dùng không tự làm láng giềng của chính mình
        np.fill_diagonal(sim_matrix, 0.0)

        self.similarity_matrix = sim_matrix
        return self

    def predict_scores(self, user_id: str) -> Optional[np.ndarray]:
        """
        Tính vector điểm dự đoán cho toàn bộ bài hát dựa trên Top K láng giềng gần nhất.
        Trả về None nếu người dùng chưa có trong ma trận hoặc không có láng giềng phù hợp.
        """
        if self.dataset is None or self.similarity_matrix.size == 0:
            return None

        uid = str(user_id)
        if uid not in self.dataset.user_to_idx:
            return None

        u_idx = self.dataset.user_to_idx[uid]
        user_sims = self.similarity_matrix[u_idx]

        valid_indices = np.where(user_sims > self.min_similarity)[0]
        if len(valid_indices) == 0:
            return None

        if self.k_neighbors > 0 and len(valid_indices) > self.k_neighbors:
            top_order = np.argsort(-user_sims[valid_indices], kind="stable")[
                : self.k_neighbors
            ]
            neighbor_indices = valid_indices[top_order]
        else:
            neighbor_indices = valid_indices

        neighbor_sims = user_sims[neighbor_indices]
        neighbor_weights = self.weighted_matrix[neighbor_indices]

        # Cộng điểm bài hát theo tích (độ tương đồng * trọng số nghe của láng giềng)
        predicted_scores = neighbor_sims @ neighbor_weights
        return predicted_scores

    def recommend(
        self,
        user_id: str,
        top_k: int = TOP_K,
        exclude_listened: bool = True,
    ) -> List[Dict]:
        """
        Trả về Top K bài hát chưa nghe có điểm dự đoán cao nhất.
        Nếu không tìm thấy láng giềng hoặc thiếu ứng viên, bù bằng Popularity (user_count).
        """
        if self.dataset is None or self.dataset.num_songs == 0 or top_k <= 0:
            return []

        scores = self.predict_scores(user_id)

        if scores is None:
            fallback_recs = self.fallback_model.recommend(
                user_id=user_id,
                top_k=top_k,
                exclude_listened=exclude_listened,
            )
            for item in fallback_recs:
                item["method"] = "popularity_fallback"
            return fallback_recs

        candidate_scores = scores.copy()
        if exclude_listened:
            u_idx = self.dataset.user_to_idx[str(user_id)]
            listened_mask = self.dataset.matrix[u_idx] > 0
            candidate_scores[listened_mask] = -1.0

        ranked_indices = np.argsort(-candidate_scores, kind="stable")

        method_name = "cosine_cf_log" if self.use_log else "cosine_cf"
        recommendations: List[Dict] = []
        picked_song_ids = set()

        for s_idx in ranked_indices:
            if candidate_scores[s_idx] <= 0.0:
                break

            song_id = self.dataset.idx_to_song[int(s_idx)]
            meta = self.dataset.song_metadata.get(song_id, {})

            recommendations.append(
                {
                    "rank": len(recommendations) + 1,
                    "song_id": song_id,
                    "title": meta.get("title", song_id),
                    "artist": meta.get("artist", "Unknown Artist"),
                    "score": float(candidate_scores[s_idx]),
                    "method": method_name,
                }
            )
            picked_song_ids.add(song_id)

            if len(recommendations) >= top_k:
                break

        if len(recommendations) < top_k:
            extra_recs = self.fallback_model.recommend(
                user_id=user_id,
                top_k=top_k + len(picked_song_ids),
                exclude_listened=exclude_listened,
            )
            for item in extra_recs:
                if item["song_id"] in picked_song_ids:
                    continue
                item["rank"] = len(recommendations) + 1
                item["method"] = "popularity_fallback"
                recommendations.append(item)
                picked_song_ids.add(item["song_id"])

                if len(recommendations) >= top_k:
                    break

        return recommendations