from django.urls import path
from .views import CreateRoom, DeleteImages, DownloadImagesZip, IndexPage, JoinRoom, RoomImages, RoomPage, UploadImages, UploadZip
urlpatterns = [
  path('', IndexPage.as_view()),
  path('room/', RoomPage.as_view()),
  path('upload-images/', UploadImages.as_view()),
  path('upload-zip/',UploadZip.as_view()),
  path('create_room/', CreateRoom.as_view()),
  path('join_room/', JoinRoom.as_view()),
  path('room-images/<str:code>/', RoomImages.as_view()),
  path('delete-images/', DeleteImages.as_view()),
  path('download-images/', DownloadImagesZip.as_view()),
]