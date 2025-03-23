from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path("ws/classroom/<int:classroom_id>/", consumers.ClassroomConsumer.as_asgi()),
]
