# Photo AI – Upload → Embeddings → Clustering Pipeline

This document explains, **function-by-function**, how the current `photo_ai/photos` Django API handles:

- Uploading images (single / multiple)
- Uploading a ZIP of images
- Storing images in Supabase Storage (room-wise folders)
- Extracting face embeddings with DeepFace (FaceNet)
- Saving embeddings in the database
- Clustering similar faces with HDBSCAN
- Returning clusters ("same person" groups)

## High-level flow

### A) Upload images (multipart)

`POST /upload-images/`

1. `UploadImages.post()` (in `photos/views.py`)
2. Upload each file to Supabase Storage (`photos/supabase_client.py`)
3. Save bytes to a temporary file (local)
4. Extract face embeddings using `represent_faces()` (in `photos/face_utils.py`)
5. Save embeddings + metadata in DB (`photos/models.py`)
6. Return per-image result (URL + face_count)

### B) Upload ZIP (multipart)

`POST /upload-zip/`

1. `UploadZip.post()`
2. Read ZIP entries safely (skip folders, non-images, big files)
3. Upload each image to Supabase
4. Temp download (local) → DeepFace embeddings
5. Save DB rows
6. Return per-image result

### C) Cluster faces for a room

`GET /cluster/?room_code=XXXXXX`

1. `ClusterFaces.get()`
2. Load all images in the room, read stored embeddings
3. Flatten embeddings into one list (each embedding = one detected face)
4. Call `cluster_faces()` (in `photos/face_cluster.py`) which runs HDBSCAN
5. Map cluster labels → images (`id`, `url`)
6. Return JSON clusters (noise label `-1` is omitted)

## Endpoints (URLs)

Defined in `photos/urls.py`:

- `POST /create_room/` → create a room and return `room_code`
- `POST /upload-images/` → upload one or many images
- `POST /upload-zip/` → upload ZIP of images
- `GET /room-images/<code>/` → list images for a room
- `GET /cluster/?room_code=<code>` → cluster faces for a room
- `POST /search-person/` → upload one photo and find matches in the room

## What each function/class does

### 1) Supabase setup

**File:** `photos/supabase_client.py`

- Loads `.env` if available.
- Creates a Supabase client using:
  - `SUPABASE_URL`
  - `SUPABASE_SERVICE_ROLE_KEY`

**Important:** this uses the *service role key*, which has elevated access. Keep it server-side only.

### 2) `UploadImages.post()`

**File:** `photos/views.py`

**Purpose:** Accepts images (1..n) for a room, stores them in Supabase, extracts face embeddings, saves to DB.

**Input:** multipart form-data

- `room_code` (or `code`)
- Files field can be any of: `images`, `image`, `files`, `file`

**Steps per file:**

1. Create a unique filename: `uuid + original_name`
2. Compute Supabase path: `<room_code>/<uuid_filename>`
3. Upload bytes to Supabase bucket `images`
4. Get public URL from Supabase
5. Save bytes to a local temp file
6. Call `represent_faces(temp_path)`
7. Extract embeddings from the result
8. Create `Image` row:
   - `room = room`
   - `image_url = public_url`
   - `embeddings = JSON string of a list of embeddings`
   - `face_count = number of embeddings`
9. Return JSON response with per-image face count

**Output (example):**

```json
{
  "message": "Images uploaded successfully",
  "count": 2,
  "total_faces": 3,
  "processed": [
    {"id": 1, "url": "https://...", "face_count": 2, "faces": [{"confidence": null, "facial_area": {}}]},
    {"id": 2, "url": "https://...", "face_count": 1, "faces": [{"confidence": null, "facial_area": {}}]}
  ]
}
```

### 3) `UploadZip.post()`

**File:** `photos/views.py`

**Purpose:** Same as `UploadImages`, but the images are inside a ZIP.

**Input:** multipart form-data

- `room_code`
- `zip_file`

**ZIP safety rules (current):**

- Skip directories inside ZIP
- Use `os.path.basename()` to avoid path traversal
- Only accept `.png`, `.jpg`, `.jpeg`
- Skip very large members (> 10MB)

Then for each image file: upload → temp file → `represent_faces()` → save embeddings → return processed list.

### 4) `represent_faces()`

**File:** `photos/face_utils.py`

**Purpose:** Wrapper around DeepFace to compute face representations.

```python
DeepFace.represent(
  img_path=image_path,
  model_name="Facenet",
  enforce_detection=False,
)
```

- Returns a list of dicts (one per detected face) when successful.
- With `enforce_detection=False`, it won’t hard-fail if a face isn’t detected.

### 5) `get_face_embeddings()`

**File:** `photos/face_utils.py`

**Purpose:** Convenience helper that converts the `represent_faces()` output into only embeddings.

- Returns `List[List[float]]` (one embedding per detected face)

Note: the upload views currently call `represent_faces()` directly (so they can also return `confidence` and `facial_area` metadata).

### 6) `cluster_faces()`

**File:** `photos/face_cluster.py`

**Purpose:** Run HDBSCAN clustering on a list of embeddings.

- Input: `embeddings_list` where each item is one face embedding
- Converts to `numpy` array `X`
- Runs:

```python
hdbscan.HDBSCAN(min_cluster_size=2, metric="euclidean")
```

- Output: list of integer labels (same length as embeddings_list)
  - `-1` means “noise / unclustered”

### 7) `ClusterFaces.get()`

**File:** `photos/views.py`

**Purpose:** Fetch all embeddings for a room, cluster them, return “person groups”.

**Input:** query string

- `room_code=XXXXXX`

**Steps:**

1. Load all `Image` rows for the room
2. For each image:
   - parse `img.embeddings` (stored JSON)
   - append each face embedding to `all_embeddings`
  - keep a mapping from each embedding back to its source image (`id`, `url`)
3. Call `labels = cluster_faces(all_embeddings)`
4. Build clusters:
   - ignore `-1`
  - group by `label` → list of images (`id`, `url`) (de-duped within each cluster)

**Output (example):**

```json
{
  "clusters": {
    "0": [{"id": 1, "url": "https://.../img1.jpg"}, {"id": 2, "url": "https://.../img2.jpg"}],
    "1": [{"id": 3, "url": "https://.../img3.jpg"}]
  }
}
```


## Search "Me" in the room

### D) Search by a query face

`POST /search-person/`

1. User uploads one query image (selfie) + `room_code`
2. Server extracts the first face embedding from the query image
3. Server compares it to all stored face embeddings in the room using cosine similarity
4. Returns images where the best similarity score is above a threshold (default `0.70`)

**Input:** multipart form-data

- `room_code` (or `code`)
- query file field can be any of: `image`, `file`, `query`, `photo`

**Output (example):**

```json
{
  "room_code": "ABC123",
  "threshold": 0.7,
  "count": 2,
  "matches": [
    {"id": 12, "url": "https://...", "score": 0.8421},
    {"id": 9, "url": "https://...", "score": 0.8012}
  ]
}
```
## Data model (DB)

**File:** `photos/models.py`

- `Room`
  - `code`: short unique identifier (used as `room_code`)

- `Image`
  - `room`: FK → `Room`
  - `image_url`: Supabase public URL
  - `embeddings`: JSON string of a list of embeddings
  - `face_count`: number of detected faces (embeddings stored)

## Notes / behaviors to be aware of

- One image can contain multiple faces → that image URL can appear in multiple clusters.
- Clustering is done on **face embeddings**, not on whole images.
- HDBSCAN can produce `-1` for embeddings that don’t fit any cluster; those are skipped.
- The Supabase path layout is: `<room_code>/<uuid_filename>` (room-wise folders).
