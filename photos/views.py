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
from urllib.parse import urlparse
from urllib.request import urlopen, Request
from .models import Image, Room
from .supabase_client import supabase
from .utils import generate_room_code


@method_decorator(ensure_csrf_cookie, name='dispatch')
class IndexPage(TemplateView):
  template_name = "photos/index.html"


@method_decorator(ensure_csrf_cookie, name='dispatch')
class RoomPage(TemplateView):
  template_name = "photos/room.html"


class UploadImages(APIView):

  def post(self,request):
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
      return Response({"error" : "Invalid room"},status = 404)
    
    uploaded_urls = []

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

      Image.objects.create(
          room=room,
          image_url=public_url
      )

      uploaded_urls.append(public_url)

    return Response({
        "message": "Images uploaded successfully",
        "count": len(uploaded_urls),
        "urls": uploaded_urls
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
        data.append({"id": img.id, "url": url})

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
    
    uploaded_urls = []
    try:
        zip_bytes = zip_file.read()
        zip_data = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except:
        return Response({"error": "Invalid ZIP file"}, status=400)

    for zip_info in zip_data.infolist():

        if zip_info.is_dir():
            continue

        file_name = zip_info.filename

        if not file_name.lower().endswith(('.png', '.jpg', '.jpeg')):
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

        Image.objects.create(
            room=room,
            image_url=public_url
        )

        uploaded_urls.append(public_url)

    return Response({
        "message": "ZIP processed successfully",
        "count": len(uploaded_urls),
        "urls": uploaded_urls
    }, status=201)    



