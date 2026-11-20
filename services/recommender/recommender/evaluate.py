from typing import Any, Dict, List, Set, Tuple

import numpy as np

from .config import RANDOM_SEED, TEST_RATIO, TOP_K
from .cosine_cf import CosineCFRecommender
from .data_prep import InteractionDataset, load_from_csv
from .popularity import PopularityRecommender


def train_test_split_dataset(
    dataset: InteractionDataset,
    test_ratio: float = TEST_RATIO,
    random_seed: int = RANDOM_SEED,
    min_songs_per_user: int = 2,
) -> Tuple[InteractionDataset, Dict[str, Set[str]]]:
    """
    Chia lịch sử nghe của từng người dùng thành:
    - train_dataset: Ma trận dùng để xây dựng mô hình (đã ẩn các bài giữ lại).
    - test_truth: Từ điển {user_id: tập song_id giữ lại để kiểm tra}.
    """
    rng = np.random.default_rng(random_seed)
    train_matrix = dataset.matrix.copy()
    test_truth: Dict[str, Set[str]] = {}

    for u_idx, user_id in enumerate(dataset.idx_to_user):
        listened_indices = np.where(dataset.matrix[u_idx] > 0)[0]
        n_listened = len(listened_indices)

        if n_listened < min_songs_per_user:
            continue

        n_test = max(1, int(round(n_listened * test_ratio)))
        n_test = min(n_test, n_listened - 1)

        test_indices = rng.choice(listened_indices, size=n_test, replace=False)
        train_matrix[u_idx, test_indices] = 0.0

        test_truth[user_id] = {
            dataset.idx_to_song[int(s_idx)] for s_idx in test_indices
        }

    train_dataset = InteractionDataset(
        matrix=train_matrix,
        user_to_idx=dataset.user_to_idx,
        idx_to_user=dataset.idx_to_user,
        song_to_idx=dataset.song_to_idx,
        idx_to_song=dataset.idx_to_song,
        song_metadata=dataset.song_metadata,
    )
    return train_dataset, test_truth


def recall_at_k(
    recommended_song_ids: List[str],
    ground_truth_song_ids: Set[str],
    k: int = TOP_K,
) -> float:
    """Recall@K = (Số bài kiểm tra xuất hiện trong Top K) / (Tổng số bài kiểm tra)."""
    if not ground_truth_song_ids or k <= 0:
        return 0.0

    top_k_preds = set(recommended_song_ids[:k])
    hits = len(top_k_preds & ground_truth_song_ids)
    return hits / len(ground_truth_song_ids)


def precision_at_k(
    recommended_song_ids: List[str],
    ground_truth_song_ids: Set[str],
    k: int = TOP_K,
) -> float:
    """Precision@K = (Số bài kiểm tra xuất hiện trong Top K) / K."""
    if k <= 0:
        return 0.0

    top_k_preds = set(recommended_song_ids[:k])
    hits = len(top_k_preds & ground_truth_song_ids)
    return hits / k


def compute_max_recall_at_k(
    test_truth: Dict[str, Set[str]],
    k: int = TOP_K,
) -> float:
    """Tính mức trần lý thuyết của Recall@K trên tập kiểm tra hiện tại."""
    if not test_truth or k <= 0:
        return 0.0

    ceilings = [
        min(k, len(truth)) / len(truth)
        for truth in test_truth.values()
        if len(truth) > 0
    ]
    return float(np.mean(ceilings)) if ceilings else 0.0


def evaluate_model(
    model: Any,
    train_dataset: InteractionDataset,
    test_truth: Dict[str, Set[str]],
    top_k: int = TOP_K,
) -> Dict[str, float]:
    """Nạp dữ liệu cho một mô hình và tính trung bình Recall@K, Precision@K và Hit Rate."""
    model.fit(train_dataset)

    recall_scores: List[float] = []
    precision_scores: List[float] = []
    hit_users = 0

    for user_id, truth_songs in test_truth.items():
        recs = model.recommend(
            user_id=user_id,
            top_k=top_k,
            exclude_listened=True,
        )
        rec_song_ids = [item["song_id"] for item in recs]

        r_score = recall_at_k(rec_song_ids, truth_songs, k=top_k)
        p_score = precision_at_k(rec_song_ids, truth_songs, k=top_k)

        recall_scores.append(r_score)
        precision_scores.append(p_score)
        if r_score > 0.0:
            hit_users += 1

    evaluated_users = len(recall_scores)
    mean_recall = float(np.mean(recall_scores)) if evaluated_users > 0 else 0.0
    mean_precision = float(np.mean(precision_scores)) if evaluated_users > 0 else 0.0
    hit_rate = (hit_users / evaluated_users) if evaluated_users > 0 else 0.0

    return {
        "evaluated_users": evaluated_users,
        "hit_users": hit_users,
        "hit_rate": hit_rate,
        "recall_at_k": mean_recall,
        "precision_at_k": mean_precision,
    }


def compare_models(
    dataset: InteractionDataset,
    models: Dict[str, Any],
    top_k: int = TOP_K,
    test_ratio: float = TEST_RATIO,
    random_seed: int = RANDOM_SEED,
) -> Dict[str, Dict[str, float]]:
    """Đánh giá và so sánh nhiều mô hình trên cùng một bộ chia train/test cố định."""
    train_dataset, test_truth = train_test_split_dataset(
        dataset=dataset,
        test_ratio=test_ratio,
        random_seed=random_seed,
    )
    max_recall = compute_max_recall_at_k(test_truth, k=top_k)

    results: Dict[str, Dict[str, float]] = {}

    print(
        f"\n--- KET QUA DANH GIA TOP-{top_k} "
        f"(Ho so: {len(test_truth)}, test_ratio={test_ratio}, seed={random_seed}, "
        f"Max Recall@{top_k} ly thuyet: {max_recall:.4f}) ---"
    )
    print(
        f"{'Mo hinh':<30} | {'Recall@' + str(top_k):<10} | "
        f"{'Precision@' + str(top_k):<12} | {'Hit Rate':<10} | {'Ho so trung'}"
    )
    print("-" * 85)

    for name, model in models.items():
        metrics = evaluate_model(
            model=model,
            train_dataset=train_dataset,
            test_truth=test_truth,
            top_k=top_k,
        )
        results[name] = metrics
        print(
            f"{name:<30} | {metrics['recall_at_k']:<10.4f} | "
            f"{metrics['precision_at_k']:<12.4f} | {metrics['hit_rate']:<10.4f} | "
            f"{metrics['hit_users']}/{metrics['evaluated_users']}"
        )

    return results


if __name__ == "__main__":
    dataset = load_from_csv(apply_limits=True)

    models_to_compare = {
        "Popularity (Play Count)": PopularityRecommender(mode="play_count"),
        "Popularity (Log Count)": PopularityRecommender(mode="log_play_count"),
        "Popularity (User Count)": PopularityRecommender(mode="user_count"),
        "Cosine CF (Raw, K=20)": CosineCFRecommender(k_neighbors=20, use_log=False),
        "Cosine CF (Log, K=10)": CosineCFRecommender(k_neighbors=10, use_log=True),
        "Cosine CF (Log, K=15)": CosineCFRecommender(k_neighbors=15, use_log=True),
        "Cosine CF (Log, K=20)": CosineCFRecommender(k_neighbors=20, use_log=True),
        "Cosine CF (Log, K=30)": CosineCFRecommender(k_neighbors=30, use_log=True),
        "Cosine CF (Log, K=50)": CosineCFRecommender(k_neighbors=50, use_log=True),
    }

    compare_models(dataset=dataset, models=models_to_compare, top_k=TOP_K)