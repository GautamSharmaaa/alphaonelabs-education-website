import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from web.models import (
    Achievement,
    BlogComment,
    BlogPost,
    Course,
    CourseMaterial,
    CourseProgress,
    Enrollment,
    ForumCategory,
    ForumReply,
    ForumTopic,
    PeerConnection,
    PeerMessage,
    Profile,
    Review,
    Session,
    SessionAttendance,
    StudyGroup,
    Subject
)


class Command(BaseCommand):
    help = "Creates test data for all models in the application"

    def clear_data(self):
        """Clear all existing data from the models."""
        self.stdout.write("Clearing existing data...")
        models = [
            BlogComment,
            BlogPost,
            PeerMessage,
            PeerConnection,
            ForumReply,
            ForumTopic,
            ForumCategory,
            Achievement,
            Review,
            CourseMaterial,
            SessionAttendance,
            CourseProgress,
            Enrollment,
            Session,
            Course,
            Subject,
            Profile,
            User,
        ]
        for model in models:
            model.objects.all().delete()
            self.stdout.write(f"Cleared {model.__name__}")

    @transaction.atomic
    def handle(self, *args, **kwargs):
        self.stdout.write("Creating test data...")

        # Clear existing data
        self.clear_data()

        # Create test users (teachers and students)
        teachers = []
        for i in range(3):
            user = User.objects.create_user(
                username=f"teacher{i}",
                email=f"teacher{i}@example.com",
                password="testpass123",
                first_name=f"Teacher{i}",
                last_name="Smith",
            )
            Profile.objects.filter(user=user).update(is_teacher=True)
            teachers.append(user)
            self.stdout.write(f"Created teacher: {user.username}")

        students = []
        for i in range(10):
            user = User.objects.create_user(
                username=f"student{i}",
                email=f"student{i}@example.com",
                password="testpass123",
                first_name=f"Student{i}",
                last_name="Doe",
            )
            students.append(user)
            self.stdout.write(f"Created student: {user.username}")

        # Create subjects
        subjects = []
        subject_data = [
            ("Programming", "Learn coding", "fas fa-code"),
            ("Mathematics", "Master math concepts", "fas fa-calculator"),
            ("Science", "Explore scientific concepts", "fas fa-flask"),
            ("Languages", "Learn new languages", "fas fa-language"),
        ]

        for name, desc, icon in subject_data:
            subject = Subject.objects.create(name=name, slug=slugify(name), description=desc, icon=icon)
            subjects.append(subject)
            self.stdout.write(f"Created subject: {subject.name}")

        # Create courses
        courses = []
        levels = ["beginner", "intermediate", "advanced"]
        for i in range(10):
            course = Course.objects.create(
                title=f"Test Course {i}",
                slug=f"test-course-{i}",
                teacher=random.choice(teachers),
                description="# Course Description\n\nThis is a test course.",
                learning_objectives="# Learning Objectives\n\n- Objective 1\n- Objective 2",
                prerequisites="# Prerequisites\n\nBasic knowledge required",
                price=Decimal(random.randint(50, 200)),
                max_students=random.randint(10, 50),
                subject=random.choice(subjects),
                level=random.choice(levels),
                status="published",
                allow_individual_sessions=random.choice([True, False]),
                invite_only=random.choice([True, False]),
            )
            courses.append(course)
            self.stdout.write(f"Created course: {course.title}")

        # Create sessions
        sessions = []
        now = timezone.now()
        for course in courses:
            for i in range(5):
                start_time = now + timedelta(days=i * 7)
                is_virtual = random.choice([True, False])
                session = Session.objects.create(
                    course=course,
                    title=f"Session {i + 1}",
                    description=f"Description for session {i + 1}",
                    start_time=start_time,
                    end_time=start_time + timedelta(hours=2),
                    price=Decimal(random.randint(20, 50)),
                    is_virtual=is_virtual,
                    meeting_link="https://meet.example.com/test" if is_virtual else "",
                    location="" if is_virtual else "Test Location",
                )
                sessions.append(session)
            self.stdout.write(f"Created sessions for course: {course.title}")

        # Create enrollments and progress
        for student in students:
            # Get list of courses student isn't enrolled in yet
            enrolled_courses = set(Enrollment.objects.filter(student=student).values_list("course_id", flat=True))
            available_courses = [c for c in courses if c.id not in enrolled_courses]

            # Enroll in random courses
            for _ in range(min(random.randint(1, 3), len(available_courses))):
                course = random.choice(available_courses)
                available_courses.remove(course)  # Remove to avoid selecting again

                enrollment = Enrollment.objects.create(student=student, course=course, status="approved")

                # Create course progress
                progress = CourseProgress.objects.create(enrollment=enrollment)
                course_sessions = Session.objects.filter(course=course)
                completed_sessions = random.sample(list(course_sessions), random.randint(0, course_sessions.count()))
                progress.completed_sessions.add(*completed_sessions)

                # Create session attendance
                for session in completed_sessions:
                    SessionAttendance.objects.create(student=student, session=session, status="completed")

                self.stdout.write(f"Created enrollment for {student.username} in {course.title}")

        # Create course materials
        material_types = ["video", "document", "quiz", "assignment"]
        for course in courses:
            for i in range(3):
                CourseMaterial.objects.create(
                    course=course,
                    title=f"Material {i + 1}",
                    description=f"Description for material {i + 1}",
                    material_type=random.choice(material_types),
                    session=random.choice(sessions) if random.choice([True, False]) else None,
                    external_url="https://localhost/default-material",  # Ensuring NOT NULL constraint
                )
            self.stdout.write(f"Created materials for course: {course.title}")

        # Create achievements
        for student in students:
            for _ in range(random.randint(1, 3)):
                Achievement.objects.create(
                    student=student,
                    course=random.choice(courses),
                    title=f"Achievement for {student.username}",
                    description="Completed a milestone",
                )

        # Create reviews
        for student in students:
            # Get courses the student is enrolled in but hasn't reviewed yet
            enrolled_courses = set(Enrollment.objects.filter(student=student).values_list("course_id", flat=True))
            reviewed_courses = set(Review.objects.filter(student=student).values_list("course_id", flat=True))
            available_courses = [c for c in courses if c.id in enrolled_courses and c.id not in reviewed_courses]

            # Create reviews for random courses
            for _ in range(min(random.randint(1, 3), len(available_courses))):
                course = random.choice(available_courses)
                available_courses.remove(course)  # Remove to avoid selecting again

                Review.objects.create(
                    student=student, course=course, rating=random.randint(3, 5), comment="Great course!"
                )

        # Create forum categories and topics
        categories = []
        for i in range(3):
            category = ForumCategory.objects.create(
                name=f"Category {i + 1}", slug=f"category-{i + 1}", description=f"Description for category {i + 1}"
            )
            categories.append(category)

            # Create topics in each category
            for j in range(3):
                topic = ForumTopic.objects.create(
                    category=category,
                    title=f"Topic {j + 1}",
                    content=f"Content for topic {j + 1}",
                    author=random.choice(students + teachers),
                )

                # Create replies
                for _ in range(random.randint(1, 5)):
                    ForumReply.objects.create(
                        topic=topic, content="This is a reply", author=random.choice(students + teachers)
                    )

        # Create peer connections and messages
        for student in students:
            # Get list of students not already connected with
            connected_peers = set(PeerConnection.objects.filter(sender=student).values_list("receiver_id", flat=True))
            connected_peers.update(PeerConnection.objects.filter(receiver=student).values_list("sender_id", flat=True))
            available_peers = [s for s in students if s != student and s.id not in connected_peers]

            # Create connections with random peers
            for _ in range(min(random.randint(1, 3), len(available_peers))):
                peer = random.choice(available_peers)
                available_peers.remove(peer)  # Remove to avoid selecting again

                PeerConnection.objects.create(sender=student, receiver=peer, status="accepted")

                # Create messages between these peers
                for _ in range(random.randint(1, 5)):
                    PeerMessage.objects.create(sender=student, receiver=peer, content="Test message")

        # Create study groups
        for course in courses:
            group = StudyGroup.objects.create(
                name=f"Study Group for {course.title}",
                description="A group for studying together",
                course=course,
                creator=random.choice(students),
                max_members=random.randint(5, 15),
            )
            # Add random members
            members = random.sample(students, random.randint(2, 5))
            group.members.add(*members)

        # Create blog posts and comments
        for teacher in teachers:
            for i in range(random.randint(1, 3)):
                post = BlogPost.objects.create(
                    title=f"Blog Post {i + 1} by {teacher.username}",
                    slug=f"blog-post-{i + 1}-by-{teacher.username}",
                    author=teacher,
                    content="# Test Content\n\nThis is a test blog post.",
                    status="published",
                    published_at=timezone.now(),
                )

                # Create comments
                for _ in range(random.randint(1, 5)):
                    BlogComment.objects.create(
                        post=post, author=random.choice(students), content="Great post!", is_approved=True
                    )

        self.stdout.write(self.style.SUCCESS("Successfully created test data"))
