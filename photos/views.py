from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import TemplateView
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import uuid
import zipfile,io
import os
import json
import requests
from urllib.parse import urlparse
from urllib.request import urlopen, Request
from .models import Image, Room
from .supabase_client import supabase
from .utils import generate_room_code
from .face_utils import represent_faces, extract_embeddings_and_meta_from_representations, get_best_face_embedding
from .face_cluster import cluster_faces

import numpy as np

@method_decorator(ensure_csrf_cookie, name='dispatch')
class IndexPage(TemplateView):
  template_name = "photos/index.html"


@method_decorator(ensure_csrf_cookie, name='dispatch')
class RoomPage(TemplateView):
  template_name = "photos/room.html"


class UploadImages(APIView):

  def post(self, request):
    room_code = request.data.get('room_code') or request.data.get('code')

    file_field_candidates = ["images", "image", "files", "file"]
    files = []
    for field in file_field_candidates:
      files = request.FILES.getlist(field)
      if files:
        break

    if not files or not room_code:
      return Response(
        {
          "error": "Missing data",
          "expected": {
            "room_code": ["room_code", "code"],
            "files": file_field_candidates,
          },
          "received": {
            "data_keys": list(request.data.keys()),
            "file_keys": list(request.FILES.keys()),
          },
        },
        status=400,
      )
    
    try:
      room = Room.objects.get(code=room_code)
    except Room.DoesNotExist:
      return Response({"error": "Invalid room"}, status=404)
    
    processed = []

    for file in files:
      
      file_name = f"{uuid.uuid4()}_{file.name}"
      file_path = f"{room.code}/{file_name}"
      file_bytes = file.read()

      try:
        supabase.storage.from_("images").upload(file_path, file_bytes)
        public_url = supabase.storage.from_("images").get_public_url(file_path)
      except Exception as exc:
        return Response({
          "error": "Supabase upload failed",
          "detail": str(exc),
        }, status=502)

      # Process faces locally from the uploaded bytes (avoid refetching from Supabase)
      ext = os.path.splitext(file.name)[1] or ".jpg"
      temp_path = f"temp_{uuid.uuid4().hex}{ext}"
      with open(temp_path, "wb") as f:
        f.write(file_bytes)

      faces = represent_faces(temp_path)
      try:
        os.remove(temp_path)
      except Exception:
        pass

      embeddings, face_meta = extract_embeddings_and_meta_from_representations(faces)

      img = Image.objects.create(
        room=room,
        image_url=public_url,
        embeddings=json.dumps(embeddings),
        face_count=len(embeddings),
      )

      processed.append({
        "id": img.id,
        "url": public_url,
        "face_count": img.face_count,
        "faces": face_meta,
      })

    return Response({
        "message": "Images uploaded successfully",
        "count": len(processed),
        "total_faces": sum((p.get("face_count") or 0) for p in processed),
        "processed": processed,
      }, status=201)


class CreateRoom(APIView):

  def post(self,request):
    name = request.data.get("name") or "Room"
    code = generate_room_code()

    while Room.objects.filter(code=code).exists():
      code = generate_room_code()

    room = Room.objects.create(
      name=name,
      code=code
    )

    return Response({
      "message": "Room created",
      "room_code": room.code
    }, status=201)


class JoinRoom(APIView):

  def post(self,request):
    code = request.data.get("code")

    try:
      room = Room.objects.get(code=code)
      return Response({
        "message": "Joined",
        "room_name": room.name
      })
    except Room.DoesNotExist:
      return Response({
        "error": "Room not found"
      }, status=404)


class RoomImages(APIView):

  def get(self,request,code):
    try:
      room = Room.objects.get(code=code)
      images = Image.objects.filter(room=room)

      data = []
      for img in images:
        url = img.image_url
        if isinstance(url, str) and "/storage/v1/object/public/iamges/" in url:
          url = url.replace("/storage/v1/object/public/iamges/", "/storage/v1/object/public/images/")
        data.append({"id": img.id, "url": url, "face_count": getattr(img, "face_count", 0) or 0})

      return Response({"images": data})
    except Room.DoesNotExist:
      return Response({"error": "Room not found"}, status=404)


def _try_get_supabase_path_from_public_url(public_url: str) -> str | None:
  try:
    parsed = urlparse(public_url)
    marker = "/storage/v1/object/public/images/"
    if marker not in parsed.path:
      return None
    return parsed.path.split(marker, 1)[1]
  except Exception:
    return None


class DeleteImages(APIView):

  def post(self, request):
    room_code = request.data.get("room_code") or request.data.get("code")
    image_ids = request.data.get("image_ids") or request.data.get("ids") or []

    if not room_code or not isinstance(image_ids, list) or not image_ids:
      return Response({
        "error": "Missing data",
        "expected": {"room_code": "str", "image_ids": "non-empty list[int]"},
      }, status=400)

    try:
      room = Room.objects.get(code=room_code)
    except Room.DoesNotExist:
      return Response({"error": "Invalid room"}, status=404)

    images = list(Image.objects.filter(room=room, id__in=image_ids))
    if not images:
      return Response({"deleted": 0})

    # Best-effort remove from Supabase storage (ignore failures)
    try:
      paths = []
      for img in images:
        p = _try_get_supabase_path_from_public_url(img.image_url)
        if p:
          paths.append(p)
      if paths:
        supabase.storage.from_("images").remove(paths)
    except Exception:
      pass

    deleted_count, _ = Image.objects.filter(room=room, id__in=[img.id for img in images]).delete()
    # Django returns (num_deleted, {"app.Model": num})
    return Response({"deleted": deleted_count})


class DeleteRoom(APIView):

  def post(self, request):
    room_code = request.data.get("room_code") or request.data.get("code")
    if not room_code:
      return Response({
        "error": "Missing data",
        "expected": {"room_code": ["room_code", "code"]},
      }, status=400)

    try:
      room = Room.objects.get(code=room_code)
    except Room.DoesNotExist:
      return Response({"error": "Room not found"}, status=404)

    # Best-effort remove all objects under this room from Supabase storage.
    try:
      images = list(Image.objects.filter(room=room))
      paths = []
      for img in images:
        p = _try_get_supabase_path_from_public_url(img.image_url)
        if p:
          paths.append(p)
      if paths:
        supabase.storage.from_("images").remove(paths)
    except Exception:
      pass

    room.delete()
    return Response({"deleted": True, "room_code": room_code})


class DownloadImagesZip(APIView):

  def post(self, request):
    room_code = request.data.get("room_code") or request.data.get("code")
    image_ids = request.data.get("image_ids") or request.data.get("ids") or []

    if not room_code or not isinstance(image_ids, list) or not image_ids:
      return Response({
        "error": "Missing data",
        "expected": {"room_code": "str", "image_ids": "non-empty list[int]"},
      }, status=400)

    try:
      room = Room.objects.get(code=room_code)
    except Room.DoesNotExist:
      return Response({"error": "Invalid room"}, status=404)

    images = list(Image.objects.filter(room=room, id__in=image_ids))
    if not images:
      return Response({"error": "No images found"}, status=404)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
      for img in images:
        url = img.image_url
        try:
          req = Request(url, headers={"User-Agent": "photo-ai-room/1.0"})
          with urlopen(req, timeout=15) as resp:
            content_type = (resp.headers.get("Content-Type") or "").lower()
            data = resp.read()

          ext = ".jpg"
          if "png" in content_type:
            ext = ".png"
          elif "jpeg" in content_type or "jpg" in content_type:
            ext = ".jpg"
          elif "webp" in content_type:
            ext = ".webp"

          zf.writestr(f"{img.id}{ext}", data)
        except Exception:
          # Skip failures rather than failing the whole ZIP
          continue

    buf.seek(0)
    filename = f"room_{room.code}_images.zip"
    response = HttpResponse(buf.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


class UploadZip(APIView):

  def post(self,request):
    room_code = request.data.get('room_code')
    zip_file = request.FILES.get('zip_file')

    if not room_code or not zip_file:
      return Response({"error" : "Missing data"},status = 400)

    try:
      room = Room.objects.get(code = room_code)
    except Room.DoesNotExist:
      return Response({"error": "Invalid room"}, status=404)
    
    processed = []
    try:
        zip_bytes = zip_file.read()
        zip_data = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except Exception:
        return Response({"error": "Invalid ZIP file"}, status=400)

    for zip_info in zip_data.infolist():

        if zip_info.is_dir():
            continue

        # Only keep the base file name to avoid directory traversal / odd paths
        file_name = os.path.basename(zip_info.filename)
        if not file_name:
          continue

        if not file_name.lower().endswith(('.png', '.jpg', '.jpeg')):
            continue

        # Basic safety: skip very large members (default 10MB)
        if getattr(zip_info, "file_size", 0) and zip_info.file_size > 10 * 1024 * 1024:
          continue

        import uuid
        file_name = f"{uuid.uuid4()}_{file_name}"

        file_data = zip_data.read(zip_info)

        file_path = f"{room.code}/{file_name}"

        try:
          supabase.storage.from_("images").upload(file_path, file_data)
          public_url = supabase.storage.from_("images").get_public_url(file_path)
        except Exception as exc:
          return Response({
            "error": "Supabase upload failed",
            "detail": str(exc),
          }, status=502)

        ext = os.path.splitext(file_name)[1] or ".jpg"
        temp_path = f"temp_{uuid.uuid4().hex}{ext}"
        with open(temp_path, "wb") as f:
          f.write(file_data)

        faces = represent_faces(temp_path)
        try:
          os.remove(temp_path)
        except Exception:
          pass

        embeddings, face_meta = extract_embeddings_and_meta_from_representations(faces)

        img = Image.objects.create(
          room=room,
          image_url=public_url,
          embeddings=json.dumps(embeddings),
          face_count=len(embeddings),
        )

        processed.append({
          "id": img.id,
          "url": public_url,
          "face_count": img.face_count,
          "faces": face_meta,
        })

    return Response({
        "message": "ZIP processed successfully",
      "count": len(processed),
      "total_faces": sum((p.get("face_count") or 0) for p in processed),
      "processed": processed,
    }, status=201)    


class ClusterFaces(APIView):

  def get(self, request):
    room_code = request.GET.get("room_code")

    # Optional tuning knobs
    try:
      min_cluster_size = int(request.GET.get("min_cluster_size") or 2)
    except Exception:
      min_cluster_size = 2

    try:
      min_samples = request.GET.get("min_samples")
      # Default to None (HDBSCAN uses min_cluster_size) for more conservative clustering.
      min_samples = None if min_samples in (None, "", "null", "None") else int(min_samples)
    except Exception:
      min_samples = None

    fallback_threshold = _safe_float(request.GET.get("fallback_threshold"), 0.62)

    prune_threshold = _safe_float(request.GET.get("prune_threshold"), 0.60)

    if not room_code:
      return Response({"error": "room_code required"}, status=400)

    images = Image.objects.filter(room__code=room_code)

    all_embeddings = []
    face_to_image = []

    for img in images:
      if not img.embeddings:
        continue

      try:
        emb_list = json.loads(img.embeddings)
      except Exception:
        continue

      if not isinstance(emb_list, list):
        continue

      for emb in emb_list:
        all_embeddings.append(emb)
        face_to_image.append({"id": img.id, "url": img.image_url})

    if not all_embeddings:
      return Response({"error": "No embeddings found"}, status=404)

    labels = cluster_faces(
      all_embeddings,
      min_cluster_size=min_cluster_size,
      min_samples=min_samples,
      fallback_threshold=fallback_threshold,
      prune_threshold=prune_threshold,
    )

    clustered_data = {}
    for label, image_ref in zip(labels, face_to_image):
      try:
        label_int = int(label)
      except Exception:
        continue

      if label_int == -1:
        continue

      # JSON object keys must be strings.
      # Each face embedding maps back to its source image; de-dupe image ids within a cluster.
      key = str(label_int)
      clustered_data.setdefault(key, [])
      if not any(x.get("id") == image_ref.get("id") for x in clustered_data[key]):
        clustered_data[key].append({"id": image_ref.get("id"), "url": image_ref.get("url")})

    return Response({"clusters": clustered_data})


def _safe_float(value, default: float) -> float:
  try:
    if value is None:
      return default
    return float(value)
  except Exception:
    return default


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
  denom = (np.linalg.norm(a) * np.linalg.norm(b))
  if denom == 0:
    return 0.0
  return float(np.dot(a, b) / denom)


class SearchPerson(APIView):

  def post(self, request):
    room_code = request.data.get('room_code') or request.data.get('code')

    file_field_candidates = ["image", "file", "query", "photo"]
    qf = None
    for field in file_field_candidates:
      qf = request.FILES.get(field)
      if qf:
        break

    if not room_code or not qf:
      return Response(
        {
          "error": "Missing data",
          "expected": {
            "room_code": ["room_code", "code"],
            "file": file_field_candidates,
          },
          "received": {
            "data_keys": list(request.data.keys()),
            "file_keys": list(request.FILES.keys()),
          },
        },
        status=400,
      )

    try:
      room = Room.objects.get(code=room_code)
    except Room.DoesNotExist:
      return Response({"error": "Room not found"}, status=404)

    threshold = _safe_float(request.data.get("threshold"), 0.70)
    # Clamp to sane range
    if threshold < 0:
      threshold = 0.0
    if threshold > 1:
      threshold = 1.0

    # Build query embedding from uploaded image
    ext = os.path.splitext(qf.name)[1] or ".jpg"
    temp_path = f"temp_query_{uuid.uuid4().hex}{ext}"
    qbytes = qf.read()
    with open(temp_path, "wb") as f:
      f.write(qbytes)

    q_embedding = get_best_face_embedding(temp_path)
    try:
      os.remove(temp_path)
    except Exception:
      pass

    if q_embedding is None:
      return Response({"error": "No face found in query image"}, status=404)

    try:
      q = np.array(q_embedding, dtype=np.float32)
    except Exception:
      return Response({"error": "Invalid embedding from query image"}, status=500)

    matches = []
    images = Image.objects.filter(room=room)
    for img in images:
      if not img.embeddings:
        continue

      try:
        emb_list = json.loads(img.embeddings)
      except Exception:
        continue

      best = 0.0
      for emb in emb_list if isinstance(emb_list, list) else []:
        try:
          v = np.array(emb, dtype=np.float32)
          score = _cosine_similarity(q, v)
          if score > best:
            best = score
        except Exception:
          continue

      if best >= threshold:
        matches.append({"id": img.id, "url": img.image_url, "score": round(best, 4)})

    matches.sort(key=lambda x: x.get("score", 0), reverse=True)
    return Response({
      "room_code": room_code,
      "threshold": threshold,
      "count": len(matches),
      "matches": matches,
    })