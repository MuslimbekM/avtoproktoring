from django.db import models
from django.contrib.auth.models import User

class Student(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    full_name = models.CharField(max_length=100)
    student_id = models.CharField(max_length=50, unique=True)
    email = models.EmailField(unique=True)

    def __str__(self):
        return self.full_name

class VideoRecording(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    video_file = models.FileField(upload_to='recordings/')

    def __str__(self):
        return f"{self.student.full_name} - {self.start_time}"

