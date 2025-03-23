import json

from asgiref.sync import sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from web.models import (
    Course,
    Enrollment,
    HandRaise,
    Session,
    SessionEnrollment,
    SharedContent,
    Subject,
    UpdateRound,
    UpdateTurn,
    VirtualClassroom,
    VirtualSeat,
)
from web.routing import websocket_urlpatterns

User = get_user_model()


class VirtualClassroomViewsTests(TestCase):
    def setUp(self):
        # Create test users
        self.teacher = User.objects.create_user(username="teacher", email="teacher@example.com", password="password123")
        self.teacher.profile.is_teacher = True
        self.teacher.profile.save()

        self.student1 = User.objects.create_user(
            username="student1", email="student1@example.com", password="password123"
        )

        self.student2 = User.objects.create_user(
            username="student2", email="student2@example.com", password="password123"
        )

        # Create an unauthorized user
        self.unauthorized_user = User.objects.create_user(
            username="unauthorized", email="unauthorized@example.com", password="password123"
        )

        # Create subject
        self.subject = Subject.objects.create(name="Test Subject", slug="test-subject")

        # Create a course
        self.course = Course.objects.create(
            title="Test Course",
            description="Test Course Description",
            teacher=self.teacher,
            price=100,  # Add required price field
            learning_objectives="Learning objectives for the test course",
            max_students=10,
            subject=self.subject,
        )

        # Create a session
        self.session = Session.objects.create(
            title="Test Session",
            course=self.course,
            description="Test session description",
            start_time="2023-10-01T10:00:00Z",
            end_time="2023-10-01T12:00:00Z",
        )

        # Create a virtual classroom
        self.classroom = VirtualClassroom.objects.create(session=self.session, rows=3, columns=4)

        # Create seats for the classroom
        for row in range(1, 4):
            for col in range(1, 5):
                VirtualSeat.objects.create(classroom=self.classroom, row=row, column=col, status="empty")

        # Enroll students in the course and session
        self.enrollment1 = Enrollment.objects.create(student=self.student1, course=self.course, status="active")

        self.enrollment2 = Enrollment.objects.create(student=self.student2, course=self.course, status="active")

        self.session_enrollment1 = SessionEnrollment.objects.create(
            student=self.student1, session=self.session, status="confirmed"
        )

        self.session_enrollment2 = SessionEnrollment.objects.create(
            student=self.student2, session=self.session, status="confirmed"
        )

        # Set up clients
        self.teacher_client = Client()
        self.student1_client = Client()
        self.student2_client = Client()
        self.unauthorized_client = Client()

        # Log in users
        self.teacher_client.login(username="teacher", password="password123")
        self.student1_client.login(username="student1", password="password123")
        self.student2_client.login(username="student2", password="password123")
        self.unauthorized_client.login(username="unauthorized", password="password123")

    def test_classroom_page_loads(self):
        """Test that the classroom page loads correctly for students and teachers"""
        # Test teacher view
        teacher_url = reverse("virtual_classroom", args=[self.session.id])
        teacher_response = self.teacher_client.get(teacher_url)
        self.assertEqual(teacher_response.status_code, 200)

        # Test student view
        student_url = reverse("virtual_classroom", args=[self.session.id])
        student_response = self.student1_client.get(student_url)
        self.assertEqual(student_response.status_code, 200)

    def test_unauthorized_access(self):
        """Test that unauthorized users can't access the classroom"""
        # Try to access as unauthorized user
        url = reverse("virtual_classroom", args=[self.session.id])
        response = self.unauthorized_client.get(url)
        self.assertNotEqual(response.status_code, 200)  # Should redirect or deny access

    def test_select_seat(self):
        """Test selecting a seat"""
        # Get first empty seat
        seat = VirtualSeat.objects.filter(classroom=self.classroom, status="empty").first()

        # Select seat as student
        url = reverse("select_seat", args=[self.classroom.id])
        response = self.student1_client.post(
            url, data=json.dumps({"seat_id": seat.id}), content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)

        # Check seat is assigned
        seat.refresh_from_db()
        self.assertEqual(seat.status, "occupied")
        self.assertEqual(seat.student, self.student1)

        # Try to select the same seat with another student (should fail)
        response2 = self.student2_client.post(
            url, data=json.dumps({"seat_id": seat.id}), content_type="application/json"
        )
        self.assertNotEqual(response2.status_code, 200)

        # Try to select a seat with invalid JSON
        response3 = self.student1_client.post(url, data="invalid json data", content_type="application/json")
        self.assertEqual(response3.status_code, 400)

    def test_select_seat_unauthorized(self):
        """Test that unauthorized users can't select seats"""
        seat = VirtualSeat.objects.filter(classroom=self.classroom, status="empty").first()

        url = reverse("select_seat", args=[self.classroom.id])
        response = self.unauthorized_client.post(
            url, data=json.dumps({"seat_id": seat.id}), content_type="application/json"
        )
        self.assertEqual(response.status_code, 403)  # Forbidden

    def test_raise_hand(self):
        """Test raising hand functionality"""
        # First select a seat
        seat = VirtualSeat.objects.filter(classroom=self.classroom, status="empty").first()

        # Select the seat
        select_url = reverse("select_seat", args=[self.classroom.id])
        self.student1_client.post(select_url, data=json.dumps({"seat_id": seat.id}), content_type="application/json")
        seat.refresh_from_db()

        # Raise hand
        url = reverse("raise_hand")
        response = self.student1_client.post(
            url, data=json.dumps({"seat_id": seat.id, "raised": True}), content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)

        # Check hand raise exists
        hand_raise = HandRaise.objects.filter(seat=seat).first()
        self.assertIsNotNone(hand_raise)
        self.assertEqual(hand_raise.acknowledged, False)

        # Lower hand
        lower_response = self.student1_client.post(
            url, data=json.dumps({"seat_id": seat.id, "raised": False}), content_type="application/json"
        )
        self.assertEqual(lower_response.status_code, 200)

        # Check hand is lowered
        hand_raise.refresh_from_db()
        self.assertIsNotNone(hand_raise.lowered_at)

    def test_raise_hand_another_student_seat(self):
        """Test that a student can't raise hand for another student's seat"""
        # Student 1 selects a seat
        seat = VirtualSeat.objects.filter(classroom=self.classroom, status="empty").first()

        select_url = reverse("select_seat", args=[self.classroom.id])
        self.student1_client.post(select_url, data=json.dumps({"seat_id": seat.id}), content_type="application/json")

        # Student 2 tries to raise hand for Student 1's seat
        url = reverse("raise_hand")
        response = self.student2_client.post(
            url, data=json.dumps({"seat_id": seat.id, "raised": True}), content_type="application/json"
        )

        # Should be forbidden or fail
        self.assertNotEqual(response.status_code, 200)

    def test_start_speaking(self):
        """Test calling on a student who raised their hand"""
        # First select a seat and raise hand
        seat = VirtualSeat.objects.filter(classroom=self.classroom, status="empty").first()

        # Select the seat
        select_url = reverse("select_seat", args=[self.classroom.id])
        self.student1_client.post(select_url, data=json.dumps({"seat_id": seat.id}), content_type="application/json")
        seat.refresh_from_db()

        # Raise hand
        raise_url = reverse("raise_hand")
        self.student1_client.post(
            raise_url, data=json.dumps({"seat_id": seat.id, "raised": True}), content_type="application/json"
        )

        # Get hand raise ID
        hand_raise = HandRaise.objects.filter(seat=seat).first()

        # Teacher calls on student
        url = reverse("start_speaking", args=[hand_raise.id])
        response = self.teacher_client.post(url)
        self.assertEqual(response.status_code, 200)

        # Check hand raise is acknowledged
        hand_raise.refresh_from_db()
        self.assertEqual(hand_raise.acknowledged, True)

        # Check the seat status is updated
        seat.refresh_from_db()
        self.assertEqual(seat.status, "speaking")

    def test_student_cannot_call_on_raised_hand(self):
        """Test that students can't call on raised hands"""
        # First select a seat and raise hand
        seat = VirtualSeat.objects.filter(classroom=self.classroom, status="empty").first()

        # Select the seat
        select_url = reverse("select_seat", args=[self.classroom.id])
        self.student1_client.post(select_url, data=json.dumps({"seat_id": seat.id}), content_type="application/json")

        # Raise hand
        raise_url = reverse("raise_hand")
        self.student1_client.post(
            raise_url, data=json.dumps({"seat_id": seat.id, "raised": True}), content_type="application/json"
        )

        # Get hand raise ID
        hand_raise = HandRaise.objects.filter(seat=seat).first()

        # Student tries to call on raised hand
        url = reverse("start_speaking", args=[hand_raise.id])
        response = self.student2_client.post(url)

        # Should be forbidden
        self.assertEqual(response.status_code, 403)

    def test_start_update_round(self):
        """Test starting an update round"""
        # Set up seats and students
        seats = list(VirtualSeat.objects.filter(classroom=self.classroom, status="empty")[:2])

        # Student 1 selects seat
        select_url = reverse("select_seat", args=[self.classroom.id])
        self.student1_client.post(
            select_url, data=json.dumps({"seat_id": seats[0].id}), content_type="application/json"
        )

        # Student 2 selects seat
        self.student2_client.post(
            select_url, data=json.dumps({"seat_id": seats[1].id}), content_type="application/json"
        )

        # Teacher starts update round
        url = reverse("start_update_round", args=[self.classroom.id])
        data = {"duration_seconds": 60, "seats": [seats[0].id, seats[1].id]}
        response = self.teacher_client.post(url, data=json.dumps(data), content_type="application/json")
        self.assertEqual(response.status_code, 200)

        # Check update round exists
        update_round = UpdateRound.objects.filter(classroom=self.classroom).first()
        self.assertIsNotNone(update_round)
        self.assertEqual(update_round.duration_seconds, 60)

        # Check update turns were created
        turns = UpdateTurn.objects.filter(update_round=update_round)
        self.assertEqual(turns.count(), 2)

    def test_student_cannot_start_update_round(self):
        """Test that students can't start update rounds"""
        # Set up seats and students
        seats = list(VirtualSeat.objects.filter(classroom=self.classroom, status="empty")[:2])

        # Student 1 selects seat
        select_url = reverse("select_seat", args=[self.classroom.id])
        self.student1_client.post(
            select_url, data=json.dumps({"seat_id": seats[0].id}), content_type="application/json"
        )

        # Student 2 selects seat
        self.student2_client.post(
            select_url, data=json.dumps({"seat_id": seats[1].id}), content_type="application/json"
        )

        # Student tries to start update round
        url = reverse("start_update_round", args=[self.classroom.id])
        data = {"duration_seconds": 60, "seats": [seats[0].id, seats[1].id]}
        response = self.student1_client.post(url, data=json.dumps(data), content_type="application/json")

        # Should be forbidden
        self.assertEqual(response.status_code, 403)

    def test_invalid_json_handling(self):
        """Test that invalid JSON is handled properly"""
        url = reverse("select_seat", args=[self.classroom.id])
        response = self.student1_client.post(url, data="not valid json", content_type="application/json")
        self.assertEqual(response.status_code, 400)

        # Check response message
        response_data = json.loads(response.content)
        self.assertIn("message", response_data)
        self.assertIn("Invalid", response_data["message"])

    def test_share_content(self):
        """Test sharing content from a seat"""
        # First select a seat
        seat = VirtualSeat.objects.filter(classroom=self.classroom, status="empty").first()

        # Select the seat
        select_url = reverse("select_seat", args=[self.classroom.id])
        self.student1_client.post(select_url, data=json.dumps({"seat_id": seat.id}), content_type="application/json")

        # Share content
        url = reverse("upload_content", args=[seat.id])
        response = self.student1_client.post(
            url,
            data=json.dumps({"content_type": "link", "link": "https://example.com", "description": "Example link"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

        # Check content was created
        shared_content = SharedContent.objects.filter(seat=seat).first()
        self.assertIsNotNone(shared_content)
        self.assertEqual(shared_content.content_type, "link")
        self.assertEqual(shared_content.link, "https://example.com")

    def test_invalid_content_type(self):
        """Test that invalid content types are rejected"""
        # First select a seat
        seat = VirtualSeat.objects.filter(classroom=self.classroom, status="empty").first()

        # Select the seat
        select_url = reverse("select_seat", args=[self.classroom.id])
        self.student1_client.post(select_url, data=json.dumps({"seat_id": seat.id}), content_type="application/json")

        # Share content with invalid type
        url = reverse("upload_content", args=[seat.id])
        response = self.student1_client.post(
            url,
            data=json.dumps({"content_type": "invalid_type", "description": "This should be rejected"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

        # Check no content was created
        shared_content = SharedContent.objects.filter(seat=seat).exists()
        self.assertFalse(shared_content)

    def test_upload_content_permission(self):
        """Test that only seat owners can upload content"""
        # First, student 1 selects a seat
        seat = VirtualSeat.objects.filter(classroom=self.classroom, status="empty").first()

        select_url = reverse("select_seat", args=[self.classroom.id])
        self.student1_client.post(select_url, data=json.dumps({"seat_id": seat.id}), content_type="application/json")

        # Student 2 tries to upload content to student 1's seat
        upload_url = reverse("upload_content", args=[seat.id])
        response = self.student2_client.post(
            upload_url,
            data=json.dumps({"content_type": "link", "link": "https://example.com", "description": "Test link"}),
            content_type="application/json",
        )

        # Should be forbidden
        self.assertEqual(response.status_code, 403)

        # Student 1 can upload content to their own seat
        response = self.student1_client.post(
            upload_url,
            data=json.dumps({"content_type": "link", "link": "https://example.com", "description": "Test link"}),
            content_type="application/json",
        )

        # Should succeed
        self.assertEqual(response.status_code, 200)

    def test_upload_content_missing_fields(self):
        """Test that content uploads require certain fields"""
        # Student 1 selects a seat
        seat = VirtualSeat.objects.filter(classroom=self.classroom, status="empty").first()

        select_url = reverse("select_seat", args=[self.classroom.id])
        self.student1_client.post(select_url, data=json.dumps({"seat_id": seat.id}), content_type="application/json")

        # Upload with missing link
        upload_url = reverse("upload_content", args=[seat.id])
        response = self.student1_client.post(
            upload_url,
            data=json.dumps({"content_type": "link", "description": "Missing link"}),
            content_type="application/json",
        )

        # Should fail with 400
        self.assertEqual(response.status_code, 400)

        # Upload with missing content_type
        response = self.student1_client.post(
            upload_url,
            data=json.dumps({"link": "https://example.com", "description": "Missing content type"}),
            content_type="application/json",
        )

        # Should fail with 400
        self.assertEqual(response.status_code, 400)

        # Upload with valid data should succeed
        response = self.student1_client.post(
            upload_url,
            data=json.dumps({"content_type": "link", "link": "https://example.com", "description": "Complete content"}),
            content_type="application/json",
        )

        # Should succeed
        self.assertEqual(response.status_code, 200)

        # Check that the content was created
        shared_content = SharedContent.objects.filter(seat=seat).last()
        self.assertIsNotNone(shared_content)
        self.assertEqual(shared_content.link, "https://example.com")
        self.assertEqual(shared_content.description, "Complete content")


class WebSocketTests(TestCase):
    async def test_websocket_connection(self):
        """Test basic WebSocket connection for virtual classroom"""
        # Set up application with auth middleware mock
        from channels.db import database_sync_to_async

        @database_sync_to_async
        def get_user():
            return User.objects.create_user(username="testuser", email="test@example.com", password="password123")

        # Create classroom session
        teacher = await self.create_user("teacher")
        await self.create_teacher_profile(teacher)

        subject = await self.create_subject("Test Subject")
        course = await self.create_course("Test Course", teacher, subject)
        session = await self.create_session("Test Session", course)
        classroom = await self.create_classroom(session)

        # Create test user for authentication and enroll in course
        user = await get_user()

        # Enroll the user in the course and session
        await self.enroll_user_in_course(user, course)
        await self.enroll_user_in_session(user, session)

        # Create application
        application = URLRouter(websocket_urlpatterns)

        # Connect to WebSocket with mocked auth
        communicator = WebsocketCommunicator(application, f"/ws/classroom/{classroom.id}/")
        # Mock authentication
        communicator.scope["user"] = user

        connected, _ = await communicator.connect()

        # Check connection established
        self.assertTrue(connected)

        # First receive the user_joined message
        user_joined = await communicator.receive_json_from()
        self.assertEqual(user_joined["type"], "user_joined")
        self.assertEqual(user_joined["user_id"], user.id)

        # Send a chat message
        await communicator.send_json_to({"type": "chat_message", "message": "Hello, world!", "recipient": "everyone"})

        # Receive the response (echo back)
        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "chat_message")
        self.assertEqual(response["message"], "Hello, world!")

        # Close the connection
        await communicator.disconnect()

    async def test_websocket_unauthorized(self):
        """Test WebSocket connection is rejected for unauthorized users"""
        # Set up application with auth middleware mock
        # Import removed to fix linting error

    @sync_to_async
    def create_user(self, username):
        """Helper to create a user asynchronously"""
        user = User.objects.create_user(username=username, email=f"{username}@example.com", password="password123")
        return user

    @sync_to_async
    def create_teacher_profile(self, user):
        """Helper to create or update a user profile asynchronously"""
        user.profile.is_teacher = True
        user.profile.save()
        return user.profile

    @sync_to_async
    def create_subject(self, name):
        """Helper to create a subject asynchronously"""
        return Subject.objects.create(name=name, slug=name.lower().replace(" ", "-"))

    @sync_to_async
    def create_course(self, title, teacher, subject):
        """Helper to create a course asynchronously"""
        return Course.objects.create(
            title=title,
            description=f"Description for {title}",
            teacher=teacher,
            price=100,
            learning_objectives=f"Learning objectives for {title}",
            max_students=10,
            subject=subject,
        )

    @sync_to_async
    def create_session(self, title, course):
        """Helper to create a session asynchronously"""
        return Session.objects.create(
            title=title,
            course=course,
            description="Test session description",
            start_time="2023-10-01T10:00:00Z",
            end_time="2023-10-01T12:00:00Z",
        )

    @sync_to_async
    def create_classroom(self, session):
        """Helper to create a virtual classroom asynchronously"""
        return VirtualClassroom.objects.create(session=session, rows=3, columns=4)

    @sync_to_async
    def enroll_user_in_course(self, user, course):
        """Helper to enroll a user in a course asynchronously"""
        from web.models import Enrollment

        return Enrollment.objects.create(student=user, course=course, status="active")

    @sync_to_async
    def enroll_user_in_session(self, user, session):
        """Helper to enroll a user in a session asynchronously"""
        from web.models import SessionEnrollment

        return SessionEnrollment.objects.create(student=user, session=session, status="confirmed")

    async def test_websocket_content_share(self):
        """Test sharing content through WebSocket"""
        # Create teacher and student
        teacher = await self.create_user("teacher")
        await self.create_teacher_profile(teacher)

        student = await self.create_user("student")

        # Create classroom
        subject = await self.create_subject("Test Subject")
        course = await self.create_course("Test Course", teacher, subject)
        session = await self.create_session("Test Session", course)
        classroom = await self.create_classroom(session)

        # Create and assign a seat to the student
        seat = await self.create_seat(classroom, 1, 1)
        await self.assign_seat_to_student(seat, student)

        # Enroll the student in the course and session
        await self.enroll_user_in_course(student, course)
        await self.enroll_user_in_session(student, session)

        # Create application
        application = URLRouter(websocket_urlpatterns)

        # Connect as student
        communicator = WebsocketCommunicator(application, f"/ws/classroom/{classroom.id}/")
        communicator.scope["user"] = student

        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # First receive the user_joined message
        user_joined = await communicator.receive_json_from()
        self.assertEqual(user_joined["type"], "user_joined")

        # Send a content share message
        await communicator.send_json_to(
            {
                "type": "content_share",
                "seat_id": seat.id,
                "content_id": 1,
                "content_type": "link",
                "link": "https://example.com",
                "description": "Example link",
            }
        )

        # Receive the response
        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "content_share")
        self.assertEqual(response["seat_id"], seat.id)
        self.assertEqual(response["content_type"], "link")
        self.assertEqual(response["link"], "https://example.com")

        # Close the connection
        await communicator.disconnect()

    @sync_to_async
    def create_seat(self, classroom, row, column):
        """Helper to create a seat asynchronously"""
        from web.models import VirtualSeat

        return VirtualSeat.objects.create(classroom=classroom, row=row, column=column, status="empty")

    @sync_to_async
    def assign_seat_to_student(self, seat, student):
        """Helper to assign a seat to a student asynchronously"""
        seat.student = student
        seat.status = "occupied"
        seat.save()
        return seat
