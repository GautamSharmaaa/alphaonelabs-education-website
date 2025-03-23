"""
WebSocket consumers for real-time features in the educational platform.

This module provides WebSocket consumers for handling real-time communication
in the virtual classroom feature. It enables features such as:
- Real-time notifications for student activities (joining, leaving)
- Seat status updates
- Hand raise notifications
- Content sharing
- Chat messaging
- Update round management
"""

import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth import get_user_model

from .models import Enrollment, SessionEnrollment, VirtualClassroom, VirtualSeat

User = get_user_model()
logger = logging.getLogger(__name__)


class ClassroomConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for virtual classroom real-time communication.

    Handles connections to classroom-specific WebSocket groups and manages
    authentication, authorization, and message routing. Provides methods for
    sending and receiving various types of classroom events and messages.
    """

    async def connect(self):
        # Get the classroom ID from the URL route
        try:
            self.classroom_id = self.scope["url_route"]["kwargs"]["classroom_id"]
            self.classroom_group_name = f"classroom_{self.classroom_id}"

            # Check if classroom exists
            classroom_exists = await self.check_classroom_exists(self.classroom_id)
            if not classroom_exists:
                logger.warning(f"Attempted connection to non-existent classroom: {self.classroom_id}")
                await self.close(code=4004)
                return

            # Check if user is authorized to join this classroom
            user = self.scope["user"]
            if not user.is_authenticated:
                logger.warning(f"Unauthenticated user tried to connect to classroom: {self.classroom_id}")
                await self.close(code=4003)
                return

            is_authorized = await self.check_user_classroom_access(user.id, self.classroom_id)
            if not is_authorized:
                logger.warning(f"Unauthorized user {user.id} tried to connect to classroom: {self.classroom_id}")
                await self.close(code=4003)
                return

            # Add the user to the classroom group
            await self.channel_layer.group_add(self.classroom_group_name, self.channel_name)

            # Also join user-specific group for direct messages
            user_group = f"user_{user.id}"
            await self.channel_layer.group_add(user_group, self.channel_name)

            # Store user_id for later use
            self.user_id = user.id

            # Announce user joined, if they're not a teacher
            is_teacher = await self.is_teacher(user.id, self.classroom_id)
            if not is_teacher:
                await self.channel_layer.group_send(
                    self.classroom_group_name, {"type": "user_joined", "user_id": user.id, "username": user.username}
                )

            await self.accept()
        except Exception as e:
            logger.error(f"Error in WebSocket connection: {str(e)}")
            await self.close(code=4000)

    async def disconnect(self, close_code):
        try:
            # Remove the user from the classroom group
            await self.channel_layer.group_discard(self.classroom_group_name, self.channel_name)

            # Also leave user-specific group
            user = self.scope["user"]
            if user.is_authenticated:
                user_group = f"user_{user.id}"
                await self.channel_layer.group_discard(user_group, self.channel_name)

                # Announce user left, if they're not a teacher
                is_teacher = await self.is_teacher(user.id, self.classroom_id)
                if not is_teacher:
                    await self.channel_layer.group_send(
                        self.classroom_group_name, {"type": "user_left", "user_id": user.id, "username": user.username}
                    )
        except Exception as e:
            logger.error(f"Error in WebSocket disconnect: {str(e)}")

    async def receive(self, text_data):
        # Receive message from WebSocket client
        try:
            data = json.loads(text_data)
            message_type = data.get("type")

            if not message_type:
                logger.warning(f"Received message without type: {text_data[:100]}")
                return

            user = self.scope["user"]
            if not user.is_authenticated:
                logger.warning(f"Unauthenticated user tried to send message type: {message_type}")
                return

            # Handle different message types
            if message_type == "seat_update":
                # Check permissions
                seat_id = data.get("seat_id")
                if not seat_id:
                    return

                # Verify user owns this seat or is a teacher
                is_authorized = await self.can_update_seat(user.id, seat_id, self.classroom_id)
                if not is_authorized:
                    return

                # Broadcast seat update to the classroom group
                await self.channel_layer.group_send(
                    self.classroom_group_name,
                    {
                        "type": "seat_update",
                        "seat_id": seat_id,
                        "status": data.get("status"),
                        "student_id": data.get("student_id"),
                        "student_name": data.get("student_name"),
                    },
                )
            elif message_type == "hand_raise":
                # Check permissions
                seat_id = data.get("seat_id")
                if not seat_id:
                    return

                # Verify user owns this seat
                is_owner = await self.is_seat_owner(user.id, seat_id)
                if not is_owner:
                    return

                # Broadcast hand raise to the classroom group
                await self.channel_layer.group_send(
                    self.classroom_group_name,
                    {
                        "type": "hand_raise",
                        "seat_id": seat_id,
                        "raised": data.get("raised", True),
                        "student_id": user.id,
                        "student_name": user.username,
                    },
                )
            elif message_type == "update_round":
                # Verify the user is the teacher
                is_teacher = await self.is_teacher(user.id, self.classroom_id)
                if not is_teacher:
                    logger.warning(f"Non-teacher user {user.id} attempted to control an update round")
                    return

                # Broadcast update round status
                await self.channel_layer.group_send(
                    self.classroom_group_name,
                    {
                        "type": "update_round",
                        "round_id": data.get("round_id"),
                        "action": data.get("action"),
                        "current_student": data.get("current_student"),
                        "remaining_time": data.get("remaining_time"),
                    },
                )
            elif message_type == "chat_message":
                # Broadcast chat message
                await self.channel_layer.group_send(
                    (
                        self.classroom_group_name
                        if data.get("recipient") == "everyone"
                        else f"user_{data.get('recipient')}"
                    ),
                    {
                        "type": "chat_message",
                        "message": data.get("message"),
                        "sender": user.username,
                        "sender_id": user.id,
                        "recipient": data.get("recipient"),
                    },
                )
            elif message_type == "content_share":
                # Verify the user owns this seat
                seat_id = data.get("seat_id")
                if not seat_id or not await self.is_seat_owner(user.id, seat_id):
                    return

                # Broadcast content share
                await self.channel_layer.group_send(
                    self.classroom_group_name,
                    {
                        "type": "content_share",
                        "seat_id": seat_id,
                        "content_id": data.get("content_id"),
                        "content_type": data.get("content_type"),
                        "link": data.get("link"),
                        "description": data.get("description"),
                    },
                )
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON received: {text_data[:100]}")
        except Exception as e:
            logger.error(f"Error in WebSocket receive: {str(e)}")

    async def user_joined(self, event):
        await self.send(
            text_data=json.dumps({"type": "user_joined", "user_id": event["user_id"], "username": event["username"]})
        )

    async def user_left(self, event):
        await self.send(
            text_data=json.dumps({"type": "user_left", "user_id": event["user_id"], "username": event["username"]})
        )

    async def seat_update(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "seat_update",
                    "seat_id": event["seat_id"],
                    "status": event["status"],
                    "student_id": event["student_id"],
                    "student_name": event["student_name"],
                }
            )
        )

    async def hand_raise(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "hand_raise",
                    "seat_id": event["seat_id"],
                    "raised": event["raised"],
                    "student_id": event["student_id"],
                    "student_name": event["student_name"],
                }
            )
        )

    async def update_round(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "update_round",
                    "round_id": event["round_id"],
                    "action": event["action"],
                    "current_student": event["current_student"],
                    "remaining_time": event["remaining_time"],
                }
            )
        )

    async def chat_message(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "chat_message",
                    "message": event["message"],
                    "sender": event.get("sender", "System"),
                    "sender_id": event.get("sender_id", 0),
                    "recipient": event.get("recipient", "everyone"),
                }
            )
        )

    async def content_share(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "content_share",
                    "seat_id": event["seat_id"],
                    "content_id": event["content_id"],
                    "content_type": event["content_type"],
                    "link": event.get("link"),
                    "description": event.get("description"),
                }
            )
        )

    @database_sync_to_async
    def check_classroom_exists(self, classroom_id):
        return VirtualClassroom.objects.filter(id=classroom_id).exists()

    @database_sync_to_async
    def check_user_classroom_access(self, user_id, classroom_id):
        try:
            classroom = VirtualClassroom.objects.get(id=classroom_id)
            session = classroom.session
            course = session.course

            # Teacher always has access
            if course.teacher_id == user_id:
                return True

            # Check if student is enrolled in the course and session
            return (
                Enrollment.objects.filter(student_id=user_id, course=course, status="active").exists()
                and SessionEnrollment.objects.filter(student_id=user_id, session=session, status="confirmed").exists()
            )
        except VirtualClassroom.DoesNotExist:
            return False
        except Exception:
            return False

    @database_sync_to_async
    def is_teacher(self, user_id, classroom_id):
        try:
            classroom = VirtualClassroom.objects.get(id=classroom_id)
            session = classroom.session
            course = session.course
            return course.teacher_id == user_id
        except VirtualClassroom.DoesNotExist:
            return False
        except Exception:
            return False

    @database_sync_to_async
    def is_seat_owner(self, user_id, seat_id):
        try:
            seat = VirtualSeat.objects.get(id=seat_id)
            return seat.student_id == user_id
        except VirtualSeat.DoesNotExist:
            return False
        except Exception:
            return False

    @database_sync_to_async
    def can_update_seat(self, user_id, seat_id, classroom_id):
        try:
            # Teacher can update any seat
            classroom = VirtualClassroom.objects.get(id=classroom_id)
            if classroom.session.course.teacher_id == user_id:
                return True

            # Student can only update their own seat
            seat = VirtualSeat.objects.get(id=seat_id)
            return seat.student_id == user_id
        except (VirtualClassroom.DoesNotExist, VirtualSeat.DoesNotExist):
            return False
        except Exception:
            return False
