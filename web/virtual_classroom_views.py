"""
Views for the virtual classroom feature of the educational platform.

This module provides views for creating and managing virtual classrooms,
allowing students and teachers to interact in a virtual environment.
Features include:
- Virtual seat selection and management
- Hand raising system
- Sharing content among participants
- Update rounds for structured discussions
- Real-time interaction through WebSockets
"""

import json
import logging
import random

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import (
    HandRaise,
    Session,
    SessionAttendance,
    SharedContent,
    UpdateRound,
    UpdateTurn,
    VirtualClassroom,
    VirtualSeat,
)

logger = logging.getLogger(__name__)


@login_required
def virtual_classroom(request, session_id):
    """Main view for the virtual classroom."""
    session = get_object_or_404(Session, id=session_id)

    # Check if user is enrolled or is the teacher
    is_teacher = request.user == session.course.teacher
    is_student = (
        session.course.enrollments.filter(student=request.user).exists()
        or session.enrollments.filter(student=request.user).exists()
    )

    if not (is_teacher or is_student):
        messages.error(request, "You must be enrolled in this course to access the virtual classroom.")
        return redirect("course_detail", slug=session.course.slug)

    # Get or create the virtual classroom
    classroom, created = VirtualClassroom.objects.get_or_create(session=session)

    # If this is a new classroom, create the seats
    if created:
        for row in range(classroom.rows):
            for col in range(classroom.columns):
                VirtualSeat.objects.create(classroom=classroom, row=row, column=col)

    # Get the user's current seat if they have one
    user_seat = VirtualSeat.objects.filter(classroom=classroom, student=request.user).first()

    # Get all seats with their status
    seats = VirtualSeat.objects.filter(classroom=classroom).order_by("row", "column")

    # Get active hand raises
    active_hand_raises = HandRaise.objects.filter(seat__classroom=classroom, lowered_at__isnull=True).select_related(
        "seat", "seat__student"
    )

    # Get active update round if any
    active_update_round = UpdateRound.objects.filter(classroom=classroom, ended_at__isnull=True).first()

    # Get current update turn if any
    current_turn = None
    if active_update_round:
        current_turn = UpdateTurn.objects.filter(update_round=active_update_round, ended_at__isnull=True).first()

    # Mark attendance for the student
    if is_student and not is_teacher:
        attendance, _ = SessionAttendance.objects.get_or_create(
            session=session, student=request.user, defaults={"status": "present"}
        )
        if attendance.status != "present":
            attendance.status = "present"
            attendance.save()

    context = {
        "session": session,
        "classroom": classroom,
        "is_teacher": is_teacher,
        "is_student": is_student,
        "seats": seats,
        "user_seat": user_seat,
        "active_hand_raises": active_hand_raises,
        "active_update_round": active_update_round,
        "current_turn": current_turn,
    }

    return render(request, "virtual_classroom/classroom.html", context)


@login_required
@require_POST
def select_seat(request, classroom_id):
    """API for selecting a seat in the classroom."""
    classroom = get_object_or_404(VirtualClassroom, id=classroom_id)

    # Check if the user is enrolled or is the teacher
    session = classroom.session
    is_teacher = request.user == session.course.teacher
    is_student = (
        session.course.enrollments.filter(student=request.user).exists()
        or session.enrollments.filter(student=request.user).exists()
    )

    if not (is_teacher or is_student):
        return JsonResponse({"success": False, "message": "You must be enrolled in this course."}, status=403)

    # Get the seat_id from the request
    try:
        if request.content_type == "application/json":
            data = json.loads(request.body)
            seat_id = data.get("seat_id")
        else:
            seat_id = request.POST.get("seat_id")

        if not seat_id:
            return JsonResponse({"success": False, "message": "Seat ID is required."}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "message": "Invalid JSON format."}, status=400)
    except Exception as e:
        return JsonResponse({"success": False, "message": f"Invalid request format: {str(e)}"}, status=400)

    with transaction.atomic():
        # Release any existing seat for this user
        VirtualSeat.objects.filter(classroom=classroom, student=request.user).update(
            student=None, status="empty", assigned_at=None
        )

        # Try to select the new seat
        try:
            seat = VirtualSeat.objects.get(classroom=classroom, id=seat_id)
            if seat.student:
                return JsonResponse({"success": False, "message": "This seat is already taken."}, status=409)

            seat.student = request.user
            seat.status = "occupied"
            seat.assigned_at = timezone.now()
            seat.save()

            return JsonResponse(
                {
                    "success": True,
                    "message": "Seat selected successfully.",
                    "seat": {
                        "id": seat.id,
                        "row": seat.row,
                        "column": seat.column,
                        "student": request.user.username,
                        "status": seat.status,
                    },
                }
            )
        except VirtualSeat.DoesNotExist:
            return JsonResponse({"success": False, "message": "Seat not found."}, status=404)


@login_required
@require_POST
def raise_hand(request):
    """API for raising/lowering hand."""
    user = request.user

    # Get the seat_id and raised status from the request
    try:
        if request.content_type == "application/json":
            data = json.loads(request.body)
            seat_id = data.get("seat_id")
            raised = data.get("raised", True)
        else:
            seat_id = request.POST.get("seat_id")
            raised = request.POST.get("raised") == "true"

        if not seat_id:
            # Use the user's current seat if seat_id is not provided
            seat = VirtualSeat.objects.filter(student=user).first()
            if not seat:
                return JsonResponse({"success": False, "message": "You must be seated to raise your hand."}, status=400)
        else:
            # Get the specified seat
            seat = get_object_or_404(VirtualSeat, id=seat_id)
            if seat.student != user:
                return JsonResponse(
                    {"success": False, "message": "You can only raise/lower your own hand."}, status=403
                )
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "message": "Invalid JSON format."}, status=400)
    except Exception as e:
        return JsonResponse({"success": False, "message": f"Invalid request format: {str(e)}"}, status=400)

    # Check if already has hand raised
    active_hand_raise = HandRaise.objects.filter(seat=seat, lowered_at__isnull=True).first()

    if active_hand_raise and not raised:
        # Lower hand
        active_hand_raise.lowered_at = timezone.now()
        active_hand_raise.save()
        seat.status = "occupied"
        seat.save()
        return JsonResponse({"success": True, "action": "lowered", "message": "Hand lowered."})
    elif not active_hand_raise and raised:
        # Raise hand
        HandRaise.objects.create(seat=seat)
        seat.status = "hand_raised"
        seat.save()
        return JsonResponse({"success": True, "action": "raised", "message": "Hand raised."})
    else:
        # No change needed
        return JsonResponse({"success": True, "action": "unchanged", "message": "No change to hand status."})


@login_required
@require_POST
def start_speaking(request, hand_raise_id):
    """Teacher selects a student to speak."""
    hand_raise = get_object_or_404(HandRaise, id=hand_raise_id, lowered_at__isnull=True)

    # Verify the user is the teacher
    session = hand_raise.seat.classroom.session
    if request.user != session.course.teacher:
        return JsonResponse({"success": False, "message": "Only the teacher can select who speaks."}, status=403)

    with transaction.atomic():
        # Mark all seats as not speaking
        VirtualSeat.objects.filter(classroom=hand_raise.seat.classroom, status="speaking").update(status="occupied")

        # Mark this student as speaking
        hand_raise.acknowledged = True
        hand_raise.save()

        seat = hand_raise.seat
        seat.status = "speaking"
        seat.save()

        return JsonResponse(
            {
                "success": True,
                "message": f"{seat.student.username} is now speaking.",
                "student": {"id": seat.student.id, "username": seat.student.username, "seat_id": seat.id},
            }
        )


@login_required
@require_POST
def upload_content(request, seat_id):
    """Upload content from a student's virtual laptop."""
    seat = get_object_or_404(VirtualSeat, id=seat_id)

    # Verify the user owns this seat
    if request.user != seat.student:
        return JsonResponse({"success": False, "message": "You can only share content from your own seat."}, status=403)

    # Get the file and content description
    try:
        if request.content_type.startswith("multipart/form-data"):
            file = request.FILES.get("file")
            content_type = request.POST.get("content_type")
            description = request.POST.get("description", "")
            link = request.POST.get("link", "")
        elif request.content_type == "application/json":
            data = json.loads(request.body)
            file = None
            content_type = data.get("content_type")
            description = data.get("description", "")
            link = data.get("link", "")
        else:
            return JsonResponse({"success": False, "message": "Unsupported content type."}, status=400)

        if not content_type:
            return JsonResponse({"success": False, "message": "Content type is required."}, status=400)

        if content_type not in ["screenshot", "document", "link"]:
            return JsonResponse({"success": False, "message": "Invalid content type."}, status=400)

        if content_type == "link" and not link:
            return JsonResponse({"success": False, "message": "Link is required for link content type."}, status=400)

        if content_type != "link" and not file and request.content_type.startswith("multipart/form-data"):
            return JsonResponse({"success": False, "message": "File is required for this content type."}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "message": "Invalid JSON format."}, status=400)
    except Exception as e:
        return JsonResponse({"success": False, "message": f"Error processing request: {str(e)}"}, status=400)

    # Handle file upload
    if file:
        shared_content = SharedContent.objects.create(
            seat=seat, content_type=content_type, file=file, description=description
        )

        return JsonResponse(
            {
                "success": True,
                "message": "Content shared successfully.",
                "content": {
                    "id": shared_content.id,
                    "type": shared_content.content_type,
                    "url": shared_content.file.url,
                    "description": shared_content.description,
                    "shared_at": shared_content.shared_at.isoformat(),
                },
            }
        )

    # Handle URL sharing
    elif link:
        shared_content = SharedContent.objects.create(
            seat=seat, content_type="link", link=link, description=description
        )

        return JsonResponse(
            {
                "success": True,
                "message": "Link shared successfully.",
                "content": {
                    "id": shared_content.id,
                    "type": "link",
                    "url": shared_content.link,
                    "description": shared_content.description,
                    "shared_at": shared_content.shared_at.isoformat(),
                },
            }
        )

    return JsonResponse({"success": False, "message": "No content provided."}, status=400)


@login_required
@require_POST
def start_update_round(request, classroom_id):
    """Start an update round for students to take turns speaking."""
    classroom = get_object_or_404(VirtualClassroom, id=classroom_id)

    # Only teachers can start update rounds
    if request.user != classroom.session.course.teacher:
        return JsonResponse({"success": False, "message": "Only teachers can start update rounds."}, status=403)

    try:
        data = json.loads(request.body)
        duration_seconds = data.get("duration_seconds", 60)  # Default 60 seconds per student
        seat_ids = data.get("seats", [])

        # If specific seats provided, use those
        occupied_seats = []
        if seat_ids:
            occupied_seats = list(
                VirtualSeat.objects.filter(classroom=classroom, id__in=seat_ids, status__in=["occupied", "speaking"])
            )
        else:
            # Otherwise use all occupied seats in the classroom
            occupied_seats = list(VirtualSeat.objects.filter(classroom=classroom, status__in=["occupied", "speaking"]))

        if not occupied_seats:
            return JsonResponse(
                {"success": False, "message": "No active seats found for the update round."}, status=400
            )
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "message": "Invalid JSON format."}, status=400)
    except Exception as e:
        return JsonResponse({"success": False, "message": f"Error processing request: {str(e)}"}, status=400)

    with transaction.atomic():
        # Create the update round
        update_round = UpdateRound.objects.create(classroom=classroom, duration_seconds=duration_seconds)

        # Select first student randomly
        first_seat = random.choice(occupied_seats)
        first_turn = UpdateTurn.objects.create(update_round=update_round, seat=first_seat)

        # Create turns for the rest of the seats
        for seat in occupied_seats:
            # Skip the first seat as we already created a turn for it
            if seat.id != first_seat.id:
                UpdateTurn.objects.create(update_round=update_round, seat=seat)

        return JsonResponse(
            {
                "success": True,
                "message": "Update round started.",
                "round": {
                    "id": update_round.id,
                    "duration_seconds": update_round.duration_seconds,
                    "started_at": update_round.started_at.isoformat(),
                },
                "current_turn": {
                    "id": first_turn.id,
                    "student": {"id": first_seat.student.id, "username": first_seat.student.username},
                    "started_at": first_turn.started_at.isoformat(),
                },
            }
        )


@login_required
@require_POST
def end_update_turn(request, turn_id):
    """Student or teacher ends the current update turn."""
    turn = get_object_or_404(UpdateTurn, id=turn_id, ended_at__isnull=True)
    update_round = turn.update_round
    classroom = update_round.classroom

    # Verify the user is either the teacher or the student speaking
    is_teacher = request.user == classroom.session.course.teacher
    is_speaking_student = request.user == turn.seat.student

    if not (is_teacher or is_speaking_student):
        return JsonResponse({"success": False, "message": "You cannot end this turn."}, status=403)

    with transaction.atomic():
        # End the current turn
        turn.ended_at = timezone.now()
        turn.save()

        # Find students who haven't gone yet
        remaining_seats = (
            VirtualSeat.objects.filter(classroom=classroom, student__isnull=False)
            .exclude(student=classroom.session.course.teacher)  # Exclude teacher
            .exclude(id__in=UpdateTurn.objects.filter(update_round=update_round).values_list("seat_id", flat=True))
        )

        if remaining_seats.exists():
            # Select next student randomly
            next_seat = random.choice(remaining_seats)
            next_turn = UpdateTurn.objects.create(update_round=update_round, seat=next_seat)

            return JsonResponse(
                {
                    "success": True,
                    "message": "Turn ended, next student selected.",
                    "completed": False,
                    "next_turn": {
                        "id": next_turn.id,
                        "student": {"id": next_seat.student.id, "username": next_seat.student.username},
                        "started_at": next_turn.started_at.isoformat(),
                    },
                }
            )
        else:
            # All students have gone, end the round
            update_round.ended_at = timezone.now()
            update_round.save()

            return JsonResponse(
                {
                    "success": True,
                    "message": "Update round completed!",
                    "completed": True,
                    "round": {
                        "id": update_round.id,
                        "duration_seconds": update_round.duration_seconds,
                        "started_at": update_round.started_at.isoformat(),
                        "ended_at": update_round.ended_at.isoformat(),
                    },
                }
            )


@login_required
def content_detail(request, content_id):
    """API for retrieving shared content details."""
    content = get_object_or_404(SharedContent, id=content_id)

    # Check permissions
    classroom = content.seat.classroom
    session = classroom.session
    is_teacher = request.user == session.course.teacher
    is_student = (
        session.course.enrollments.filter(student=request.user).exists()
        or session.enrollments.filter(student=request.user).exists()
    )

    if not (is_teacher or is_student):
        return JsonResponse({"success": False, "message": "Access denied"}, status=403)

    # Format the content based on its type
    content_data = {
        "id": content.id,
        "content_type": content.content_type,
        "shared_at": content.shared_at.isoformat(),
    }

    if content.content_type == "code":
        # For code content stored in the description field
        try:
            code_data = json.loads(content.description)
            content_data["content"] = {
                "code": code_data.get("code", ""),
                "language": code_data.get("language", "python"),
            }
        except json.JSONDecodeError:
            content_data["content"] = {"code": content.description, "language": "text"}
    elif content.content_type == "notes":
        content_data["content"] = {"notes": content.description}
    elif content.content_type == "document":
        content_data["content"] = {"file": content.file.url if content.file else "", "description": content.description}
    elif content.content_type == "link":
        content_data["content"] = {"link": content.link, "description": content.description}

    return JsonResponse(content_data)


@login_required
def raised_hands(request, classroom_id):
    """API for retrieving the current raised hands queue."""
    classroom = get_object_or_404(VirtualClassroom, id=classroom_id)

    # Check permissions
    session = classroom.session
    is_teacher = request.user == session.course.teacher
    is_student = (
        session.course.enrollments.filter(student=request.user).exists()
        or session.enrollments.filter(student=request.user).exists()
    )

    if not (is_teacher or is_student):
        return JsonResponse({"success": False, "message": "Access denied"}, status=403)

    # Get active hand raises
    active_hand_raises = HandRaise.objects.filter(seat__classroom=classroom, lowered_at__isnull=True).select_related(
        "seat", "seat__student"
    )

    queue = []
    for hand_raise in active_hand_raises:
        if hand_raise.seat.student:
            queue.append(
                {
                    "id": hand_raise.id,
                    "student": {"id": hand_raise.seat.student.id, "username": hand_raise.seat.student.username},
                    "seat_id": hand_raise.seat.id,
                    "raised_at": hand_raise.raised_at.isoformat(),
                }
            )

    return JsonResponse({"success": True, "queue": queue})
