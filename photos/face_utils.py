import os


def _env_bool(name: str, default: bool) -> bool:
  raw = os.environ.get(name)
  if raw is None:
    return default
  return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_float(name: str, default: float) -> float:
  raw = os.environ.get(name)
  if raw is None:
    return default
  try:
    return float(raw)
  except Exception:
    return default


def _env_int(name: str, default: int) -> int:
  raw = os.environ.get(name)
  if raw is None:
    return default
  try:
    return int(raw)
  except Exception:
    return default


def represent_faces(
  image_path: str,
  *,
  model_name: str = "Facenet",
  enforce_detection: bool | None = None,
  detector_backend: str | None = None,
  align: bool = True,
):
  """Return DeepFace representations as a list of dicts.

  Key defaults are chosen to avoid storing embeddings for non-faces:
  - enforce_detection defaults to env `DEEPFACE_ENFORCE_DETECTION` (default: true)
  - detector_backend can be set with env `DEEPFACE_DETECTOR_BACKEND`
  """

  if enforce_detection is None:
    enforce_detection = _env_bool("DEEPFACE_ENFORCE_DETECTION", True)

  if detector_backend is None:
    detector_backend = os.environ.get("DEEPFACE_DETECTOR_BACKEND") or None

  try:
    try:
      from deepface import DeepFace
    except Exception as imp_exc:
      print("DeepFace import error:", imp_exc)
      return []

    kwargs = {}
    if detector_backend:
      kwargs["detector_backend"] = detector_backend

    result = DeepFace.represent(
      img_path=image_path,
      model_name=model_name,
      enforce_detection=enforce_detection,
      align=align,
      **kwargs,
    )

    # DeepFace may return a dict for single-face; normalize to list.
    if isinstance(result, dict):
      return [result]
    return result or []
  except Exception as e:
    # Common case: no face detected when enforce_detection=True.
    print("DeepFace.represent error:", e)
    return []


def _get_face_box_wh(rep: dict) -> tuple[int | None, int | None]:
  area = rep.get("facial_area") if isinstance(rep, dict) else None
  if not isinstance(area, dict):
    return (None, None)

  w = area.get("w")
  h = area.get("h")
  if w is None:
    w = area.get("width")
  if h is None:
    h = area.get("height")

  try:
    w = int(w) if w is not None else None
  except Exception:
    w = None
  try:
    h = int(h) if h is not None else None
  except Exception:
    h = None
  return (w, h)


def filter_face_representations(
  representations,
  *,
  min_confidence: float | None = None,
  min_box_size: int | None = None,
):
  """Filter weak detections.

  Defaults are env-driven so you can tune without code changes:
  - FACE_MIN_CONFIDENCE (default 0.90)  (set <=0 to disable)
  - FACE_MIN_BOX_SIZE (default 40)      (set <=0 to disable)
  """
  if min_confidence is None:
    min_confidence = _env_float("FACE_MIN_CONFIDENCE", 0.90)
  if min_box_size is None:
    min_box_size = _env_int("FACE_MIN_BOX_SIZE", 40)

  try:
    min_confidence = float(min_confidence)
  except Exception:
    min_confidence = 0.0
  try:
    min_box_size = int(min_box_size)
  except Exception:
    min_box_size = 0

  reps = representations or []
  if isinstance(reps, dict):
    reps = [reps]

  out = []
  for r in reps:
    if not isinstance(r, dict):
      continue
    emb = r.get("embedding")
    if emb is None:
      continue

    # Confidence filter (if confidence is present)
    conf = r.get("confidence")
    if conf is not None and min_confidence > 0:
      try:
        if float(conf) < min_confidence:
          continue
      except Exception:
        pass

    # Bounding-box size filter (if facial_area is present)
    if min_box_size > 0:
      w, h = _get_face_box_wh(r)
      if w is not None and h is not None:
        if w < min_box_size or h < min_box_size:
          continue

    out.append(r)

  return out


def extract_embeddings_and_meta_from_representations(
  representations,
  *,
  min_confidence: float | None = None,
  min_box_size: int | None = None,
):
  reps = filter_face_representations(
    representations,
    min_confidence=min_confidence,
    min_box_size=min_box_size,
  )
  embeddings = [r.get("embedding") for r in reps if r.get("embedding") is not None]
  face_meta = [
    {
      "confidence": r.get("confidence"),
      "facial_area": r.get("facial_area"),
    }
    for r in reps
  ]
  return embeddings, face_meta


def get_face_embeddings(image_path: str):
  faces = represent_faces(image_path)
  embeddings, _ = extract_embeddings_and_meta_from_representations(faces)
  return embeddings


def get_best_face_embedding(image_path: str):
  """Return a single embedding for the most likely face in the image."""
  faces = represent_faces(image_path)
  reps = filter_face_representations(faces)
  if not reps:
    return None

  # Prefer highest-confidence detection, otherwise keep first.
  def _score(rep: dict) -> float:
    c = rep.get("confidence")
    try:
      return float(c) if c is not None else -1.0
    except Exception:
      return -1.0

  best = max(reps, key=_score)
  return best.get("embedding")

