import os

import django

from web.models import VirtualClassroom, VirtualSeat

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web.settings")
django.setup()

classroom = VirtualClassroom.objects.get(id=1)
for i in range(12):
    VirtualSeat.objects.create(classroom=classroom, position=i)

print("Created 12 seats")
