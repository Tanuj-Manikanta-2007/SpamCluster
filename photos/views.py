from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Image
from .supabase_client import supabase

class UploadImage(APIView):

  def post(self,request):
    file = request.FILES.get('image')

    if not file:
      return Response({"error" : "No file provided" },status = 400)
    
    file_name = file.name

    file_bytes = file.read()

    supabase.storage.from_("images").upload(file_name,file_bytes)

    public_url = supabase.storage.from_("images").get_public_url(file_name)

    image = Image.objects.create(image_url = public_url)

    return Response(
      {
        "message" : "Uploaded successfully",
        "url" : public_url
      },status = 201
    )
