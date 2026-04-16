from django.db import models


class Image(models.Model):
  image_url = models.TextField()
  uploaded_at = models.DateTimeField(auto_now_add = True)

  def __str__(self):
    return self.image_url
  
class Room(models.Model):
  name = models.CharField(max_length = 255)
  code = models.CharField(max_length = 10,unique = True)
   # password = models.CharField(max_length=100, blank=True, null=True) 
  created_at = models.DateTimeField(auto_now_add=  True)

  