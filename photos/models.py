from django.db import models


class Room(models.Model):
  name = models.CharField(max_length = 255)
  code = models.CharField(max_length = 10,unique = True)
   # password = models.CharField(max_length=100, blank=True, null=True) 
  created_at = models.DateTimeField(auto_now_add=  True)

  def __str__(self):
    return f"{self.name} ({self.code})"


class Image(models.Model):
  room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="images", null=True, blank=True)
  image_url = models.TextField()
  uploaded_at = models.DateTimeField(auto_now_add = True)

  def __str__(self):
    return self.image_url

  