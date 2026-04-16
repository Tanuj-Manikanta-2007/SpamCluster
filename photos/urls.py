from photos.views import UploadImage
from django.urls import path
urlpatterns = [
  path('upload/',UploadImage.as_view()),
]