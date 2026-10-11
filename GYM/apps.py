from django.apps import AppConfig
from django.apps import AppConfig
class TrainersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.trainers'
    
    def ready(self):
        # Don't import models here unless necessary
        pass

