from django.test import SimpleTestCase
from django.urls import resolve, reverse

from web.virtual_classroom_views import (
    content_detail,
    end_update_turn,
    raise_hand,
    raised_hands,
    select_seat,
    start_speaking,
    start_update_round,
    upload_content,
    virtual_classroom,
)


class UrlsTest(SimpleTestCase):
    """Test URL configuration for the application."""

    def test_virtual_classroom_urls(self):
        """Test URL routing for virtual classroom related views."""
        # Virtual classroom URLs
        url = reverse("virtual_classroom", args=[1])
        self.assertEqual(resolve(url).func, virtual_classroom)

        url = reverse("select_seat", args=[1])
        self.assertEqual(resolve(url).func, select_seat)

        # Hand raise doesn't take args in the URL pattern
        url = reverse("raise_hand")
        self.assertEqual(resolve(url).func, raise_hand)

        url = reverse("start_speaking", args=[1])
        self.assertEqual(resolve(url).func, start_speaking)

        url = reverse("upload_content", args=[1])
        self.assertEqual(resolve(url).func, upload_content)

        url = reverse("start_update_round", args=[1])
        self.assertEqual(resolve(url).func, start_update_round)

        url = reverse("end_update_turn", args=[1])
        self.assertEqual(resolve(url).func, end_update_turn)

        url = reverse("content_detail", args=[1])
        self.assertEqual(resolve(url).func, content_detail)

        url = reverse("raised_hands", args=[1])
        self.assertEqual(resolve(url).func, raised_hands)
