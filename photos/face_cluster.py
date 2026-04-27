import numpy as np

def _l2_normalize_rows(X: np.ndarray) -> np.ndarray:
  norms = np.linalg.norm(X, axis=1, keepdims=True)
  norms[norms == 0] = 1.0
  return X / norms


def _cosine_similarity_matrix(X: np.ndarray) -> np.ndarray:
  # X must already be L2-normalized
  return X @ X.T


def _reindex_non_negative_labels(labels: list[int]) -> list[int]:
  mapping: dict[int, int] = {}
  next_label = 0
  out: list[int] = []
  for x in labels:
    if x < 0:
      out.append(-1)
      continue
    if x not in mapping:
      mapping[x] = next_label
      next_label += 1
    out.append(mapping[x])
  return out


def _prune_by_centroid_cosine(
  Xn: np.ndarray,
  labels: list[int],
  *,
  min_cluster_size: int,
  prune_threshold: float,
) -> list[int]:
  """Prune obvious outliers inside each cluster.

  For each cluster, compute centroid (mean embedding, then L2-normalize).
  Any member with cosine(sim) < prune_threshold becomes noise (-1).
  Clusters that fall below min_cluster_size after pruning are discarded.
  """
  if prune_threshold <= 0:
    return labels

  n = int(Xn.shape[0])
  if n == 0:
    return labels

  labels_arr = np.asarray(labels, dtype=np.int32)
  unique = sorted(set(int(x) for x in labels_arr.tolist() if int(x) >= 0))
  if not unique:
    return labels

  # First pass: prune low-sim members
  for lab in unique:
    idx = np.where(labels_arr == lab)[0]
    if idx.size == 0:
      continue
    centroid = Xn[idx].mean(axis=0)
    norm = float(np.linalg.norm(centroid))
    if norm == 0:
      labels_arr[idx] = -1
      continue
    centroid = centroid / norm
    sims = Xn[idx] @ centroid
    drop = idx[sims < prune_threshold]
    if drop.size:
      labels_arr[drop] = -1

  # Second pass: drop clusters that became too small
  for lab in unique:
    idx = np.where(labels_arr == lab)[0]
    if idx.size < min_cluster_size:
      labels_arr[idx] = -1

  return [int(x) for x in labels_arr.tolist()]


def _threshold_clusters_cosine(X: np.ndarray, threshold: float) -> list[int]:
  """Fallback clustering using a cosine similarity threshold.

  This is used when HDBSCAN isn't available (or returns all noise).

  Implementation is greedy centroid assignment (fast, avoids O(n^2) scans):
  - iterate embeddings in order
  - assign to the most similar existing centroid if sim>=threshold
  - otherwise start a new cluster
  - clusters of size < 2 become noise (-1)

  Note: X must be L2-normalized.
  """
  n = int(X.shape[0])
  if n == 0:
    return []
  if n == 1:
    return [-1]

  t = float(threshold)
  if t < 0.0:
    t = 0.0
  if t > 1.0:
    t = 1.0

  # Each cluster keeps a running sum for centroid updates.
  cluster_sums: list[np.ndarray] = []
  cluster_counts: list[int] = []
  cluster_members: list[list[int]] = []

  def _norm(v: np.ndarray) -> np.ndarray:
    denom = float(np.linalg.norm(v))
    if denom == 0.0:
      return v
    return v / denom

  centroids: list[np.ndarray] = []

  for i in range(n):
    xi = X[i]
    best_k = -1
    best_sim = -1.0

    for k, c in enumerate(centroids):
      s = float(xi @ c)
      if s > best_sim:
        best_sim = s
        best_k = k

    if best_k >= 0 and best_sim >= t:
      cluster_sums[best_k] = cluster_sums[best_k] + xi
      cluster_counts[best_k] += 1
      cluster_members[best_k].append(i)
      centroids[best_k] = _norm(cluster_sums[best_k] / float(cluster_counts[best_k]))
    else:
      cluster_sums.append(xi.copy())
      cluster_counts.append(1)
      cluster_members.append([i])
      centroids.append(xi.copy())

  labels = [-1] * n
  next_label = 0
  for members in cluster_members:
    if len(members) < 2:
      continue
    for idx in members:
      labels[idx] = next_label
    next_label += 1

  return labels


def cluster_faces(
  embeddings_list,
  *,
  min_cluster_size: int = 2,
  min_samples: int | None = 1,
  fallback_threshold: float = 0.62,
  prune_threshold: float = 0.60,
):
  if not embeddings_list:
    return []

  try:
    X = np.asarray(embeddings_list, dtype=np.float32)
  except Exception:
    return []

  if X.ndim != 2 or X.shape[0] == 0:
    return []

  # FaceNet embeddings cluster better if normalized; euclidean on normalized ~= cosine distance.
  Xn = _l2_normalize_rows(X)

  if min_cluster_size < 2:
    min_cluster_size = 2

  if min_samples is not None and min_samples < 1:
    min_samples = 1

  labels = None
  try:
    import hdbscan  # type: ignore
  except Exception as imp_exc:
    hdbscan = None
    # Don't hard-fail if the environment doesn't have hdbscan.
    # We'll fall back to cosine-threshold clustering below.
    # (This also allows Django to import the module without hdbscan installed.)
    # print("hdbscan import error:", imp_exc)

  if hdbscan is not None:
    clusterer = hdbscan.HDBSCAN(
      min_cluster_size=min_cluster_size,
      min_samples=min_samples,
      metric='euclidean',
    )
    labels = clusterer.fit_predict(Xn)

  # If everything is noise (-1), use a similarity-threshold fallback.
  if labels is None:
    has_cluster = False
  else:
    try:
      has_cluster = bool(np.any(labels >= 0))
    except Exception:
      has_cluster = any(int(x) >= 0 for x in labels)

  # Fallback: cosine-threshold connected components (less strict, helps small datasets)
  if (labels is None or not has_cluster) and Xn.shape[0] >= 2:
    t = float(fallback_threshold)
    if t < 0.0:
      t = 0.0
    if t > 1.0:
      t = 1.0
    labels = np.array(_threshold_clusters_cosine(Xn, threshold=t), dtype=np.int32)

  # Post-process: prune mixed clusters by centroid similarity
  labels_list: list[int]
  try:
    labels_list = labels.astype(int).tolist()
  except Exception:
    labels_list = [int(x) for x in labels]

  pt = float(prune_threshold)
  if pt < 0.0:
    pt = 0.0
  if pt > 1.0:
    pt = 1.0
  labels_list = _prune_by_centroid_cosine(
    Xn,
    labels_list,
    min_cluster_size=min_cluster_size,
    prune_threshold=pt,
  )

  # Make labels stable and compact (0..k-1)
  labels_list = _reindex_non_negative_labels(labels_list)

  # Ensure JSON-serializable plain Python ints
  return labels_list