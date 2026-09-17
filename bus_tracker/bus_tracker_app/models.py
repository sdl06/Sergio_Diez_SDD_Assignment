from django.db import models

# Create your models here.

class Student(models.Model):
    name = models.CharField()
    date_of_birth = models.DateField()
    route = models.ForeignKey()
    assigned_stop = models.ForeignKey()

    def __str__(self):
        return self.name

class Monitor(models.Model):
    name = models.CharField()
    route = models.ForeignKey()

    def __str__(self):
        return self.name
