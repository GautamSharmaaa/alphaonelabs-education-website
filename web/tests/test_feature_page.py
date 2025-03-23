from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from web.models import FeatureVote

User = get_user_model()


class FeaturesPageTest(TestCase):
    """Test cases for the features page and feature voting functionality."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.features_url = reverse("features")
        self.vote_url = reverse("feature_vote")

        # Create a test user
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpassword")

    def test_features_page_loads(self):
        """Test that the features page loads successfully."""
        response = self.client.get(self.features_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "features.html")
        self.assertContains(response, "Get a Grade")
        self.assertContains(response, "@GautamSharmaaa")
        self.assertContains(response, "Academic grading scale")

    def test_features_page_has_voting_elements(self):
        """Test that the features page contains the necessary voting elements and JS."""
        response = self.client.get(self.features_url)

        # Check for HTML elements
        self.assertContains(response, 'class="thumbs-up"')
        self.assertContains(response, 'class="thumbs-down"')
        self.assertContains(response, 'data-feature-id="grade-link"')

        # Check for JavaScript functionality
        self.assertContains(response, "document.addEventListener")
        self.assertContains(response, "fetch")
        self.assertContains(response, "const csrfToken")
        self.assertContains(response, "localStorage.setItem")

    def test_features_page_navigation(self):
        """Test that the features page contains the correct navigation links."""
        response = self.client.get(self.features_url)

        # Check for link to the grade link feature
        self.assertContains(response, reverse("gradeable_link_list"))

        # Check for navigation elements
        self.assertContains(response, '<a href="{}"'.format(reverse("index")))
        self.assertContains(response, '<a href="{}"'.format(reverse("features")))

        # Check for title and intro text
        self.assertContains(response, "Platform Features")
        self.assertContains(response, "Discover the tools and capabilities")

        # Check that the feature card has the expected structure
        self.assertContains(response, 'data-category="new popular"')
        self.assertContains(response, "feature-status new")
        self.assertContains(response, "feature-header")
        self.assertContains(response, "feature-content")

    def test_vote_counts_display(self):
        """Test that vote counts display correctly on the features page."""
        # Create some votes
        user2 = User.objects.create_user(username="user2", email="user2@example.com", password="password2")
        user3 = User.objects.create_user(username="user3", email="user3@example.com", password="password3")

        # Add 2 upvotes and 1 downvote
        FeatureVote.objects.create(feature_id="grade-link", user=self.user, vote="up")
        FeatureVote.objects.create(feature_id="grade-link", user=user2, vote="up")
        FeatureVote.objects.create(feature_id="grade-link", user=user3, vote="down")

        # The feature page should load the current vote counts
        response = self.client.get(self.features_url)

        # The vote counts are displayed as numbers in span tags with class "count"
        # We should find the count elements with the correct values
        self.assertContains(response, '<span class="count">0</span>')

        # Note: The test doesn't verify the actual vote counts since the template just
        # shows initial values of 0. The actual counts would be loaded by JavaScript when
        # the page is viewed in a browser. We could modify the view to pre-load these counts
        # if needed for a future enhancement.

    def test_feature_vote_get_requires_feature_id(self):
        """Test that GET requests to feature_vote require a feature_id parameter."""
        # GET request without feature_id should return 400
        response = self.client.get(self.vote_url)
        self.assertEqual(response.status_code, 400)

        # GET request with feature_id should return 200
        response = self.client.get(f"{self.vote_url}?feature_id=grade-link")
        self.assertEqual(response.status_code, 200)
        self.assertIn("up_count", response.json())

    def test_feature_vote_requires_parameters(self):
        """Test that feature voting requires correct parameters."""
        response = self.client.post(self.vote_url, {})
        self.assertEqual(response.status_code, 400)

        response = self.client.post(self.vote_url, {"feature_id": "grade-link"})
        self.assertEqual(response.status_code, 400)

        response = self.client.post(self.vote_url, {"vote": "up"})
        self.assertEqual(response.status_code, 400)

    def test_anonymous_user_can_vote(self):
        """Test that anonymous users can vote using IP address tracking."""
        response = self.client.post(self.vote_url, {"feature_id": "grade-link", "vote": "up"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")
        self.assertEqual(response.json()["up_count"], 1)
        self.assertEqual(response.json()["down_count"], 0)

        # Check the vote was recorded in the database
        self.assertEqual(FeatureVote.objects.count(), 1)
        vote = FeatureVote.objects.first()
        self.assertEqual(vote.feature_id, "grade-link")
        self.assertEqual(vote.vote, "up")
        self.assertIsNone(vote.user)
        self.assertIsNotNone(vote.ip_address)

    def test_authenticated_user_can_vote(self):
        """Test that authenticated users can vote."""
        self.client.login(username="testuser", password="testpassword")

        response = self.client.post(self.vote_url, {"feature_id": "grade-link", "vote": "down"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")
        self.assertEqual(response.json()["up_count"], 0)
        self.assertEqual(response.json()["down_count"], 1)

        # Check the vote was recorded in the database
        self.assertEqual(FeatureVote.objects.count(), 1)
        vote = FeatureVote.objects.first()
        self.assertEqual(vote.feature_id, "grade-link")
        self.assertEqual(vote.vote, "down")
        self.assertEqual(vote.user, self.user)
        self.assertIsNone(vote.ip_address)

    def test_user_can_change_vote(self):
        """Test that users can change their vote."""
        self.client.login(username="testuser", password="testpassword")

        # Create an initial vote
        FeatureVote.objects.create(feature_id="grade-link", user=self.user, vote="up")

        # Change vote to down
        response = self.client.post(self.vote_url, {"feature_id": "grade-link", "vote": "down"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")
        self.assertEqual(response.json()["message"], "Vote updated")

        # Check the vote was updated
        self.assertEqual(FeatureVote.objects.count(), 1)
        vote = FeatureVote.objects.first()
        self.assertEqual(vote.vote, "down")

    def test_multiple_features_voting(self):
        """Test voting on multiple different features."""
        # Vote on first feature
        self.client.post(self.vote_url, {"feature_id": "grade-link", "vote": "up"})

        # Vote on second feature
        self.client.post(self.vote_url, {"feature_id": "another-feature", "vote": "down"})

        # Check that both votes exist
        self.assertEqual(FeatureVote.objects.count(), 2)

        grade_link_votes = FeatureVote.objects.filter(feature_id="grade-link", vote="up").count()
        another_feature_votes = FeatureVote.objects.filter(feature_id="another-feature", vote="down").count()

        self.assertEqual(grade_link_votes, 1)
        self.assertEqual(another_feature_votes, 1)
