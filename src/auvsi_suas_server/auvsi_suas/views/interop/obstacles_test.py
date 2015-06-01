"""Tests for the obstacles module."""

import time
import json
import logging
from auvsi_suas.models import AerialPosition
from auvsi_suas.models import GpsPosition
from auvsi_suas.models import MovingObstacle
from auvsi_suas.models import ObstacleAccessLog
from auvsi_suas.models import StationaryObstacle
from auvsi_suas.models import Waypoint
from django.conf import settings
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.test import TestCase
from django.test.client import Client


login_url = reverse('auvsi_suas:login')
obstacle_url = reverse('auvsi_suas:obstacles')


class TestObstaclesViewLoggedOut(TestCase):

    def test_not_authenticated(self):
        """Tests requests that have not yet been authenticated."""
        response = self.client.get(obstacle_url)
        self.assertEqual(400, response.status_code)

class TestObstaclesView(TestCase):
    """Tests the getObstacles view."""

    def create_stationary_obstacle(self, lat, lon, radius, height):
        """Create a new StationaryObstacle model.

        Args:
            lat: Latitude of centroid
            lon: Longitude of centroid
            radius: Cylinder radius
            height: Cylinder height

        Returns:
            Saved StationaryObstacle
        """
        gps = GpsPosition(latitude=lat, longitude=lon)
        gps.save()

        obstacle = StationaryObstacle(gps_position=gps,
                                      cylinder_radius=radius,
                                      cylinder_height=height)
        obstacle.save()
        return obstacle

    def create_moving_obstacle(self, waypoints):
        """Create a new MovingObstacle model.

        Args:
            waypoints: List of (lat, lon, alt) tuples

        Returns:
            Saved MovingObstacle
        """
        obstacle = MovingObstacle(speed_avg=40, sphere_radius=100)
        obstacle.save()

        for num, waypoint in enumerate(waypoints):
            (lat, lon, alt) = waypoint

            gps = GpsPosition(latitude=lat, longitude=lon)
            gps.save()

            pos = AerialPosition(gps_position=gps, altitude_msl=alt)
            pos.save()

            waypoint = Waypoint(order=num, position=pos)
            waypoint.save()

            obstacle.waypoints.add(waypoint)

        obstacle.save()
        return obstacle

    def setUp(self):
        self.user = User.objects.create_user(
                'testuser', 'email@example.com', 'testpass')
        self.user.save()

        # Add a couple of stationary obstacles
        self.create_stationary_obstacle(lat=38.142233,
                                        lon=-76.434082,
                                        radius=300,
                                        height=500)

        self.create_stationary_obstacle(lat=38.442233,
                                        lon=-76.834082,
                                        radius=100,
                                        height=750)

        # And a couple of moving obstacles
        self.create_moving_obstacle([
            # (lat,     lon,        alt)
            (38.142233, -76.434082, 300),
            (38.141878, -76.425198, 700),
        ])

        self.create_moving_obstacle([
            # (lat,     lon,        alt)
            (38.145405, -76.428310, 100),
            (38.146582, -76.424099, 200),
            (38.144662, -76.427634, 300),
            (38.147729, -76.419185, 200),
            (38.147573, -76.420832, 100),
            (38.148522, -76.419507, 750),
        ])

        # Login
        response = self.client.post(login_url, {
            'username': 'testuser',
            'password': 'testpass'
        })
        self.assertEqual(200, response.status_code)

    def test_post(self):
        """POST requests are not allowed."""
        response = self.client.post(obstacle_url)
        self.assertEqual(400, response.status_code)

    def test_correct_json(self):
        """Tests that access is logged and returns valid response."""
        response = self.client.get(obstacle_url)
        self.assertEqual(200, response.status_code)

        data = json.loads(response.content)

        self.assertIn('stationary_obstacles', data)
        self.assertEqual(2, len(data['stationary_obstacles']))
        for obstacle in data['stationary_obstacles']:
            self.assertIn('latitude', obstacle)
            self.assertIn('longitude', obstacle)
            self.assertIn('cylinder_radius', obstacle)
            self.assertIn('cylinder_height', obstacle)

        self.assertIn('moving_obstacles', data)
        self.assertEqual(2, len(data['moving_obstacles']))
        for obstacle in data['moving_obstacles']:
            self.assertIn('latitude', obstacle)
            self.assertIn('longitude', obstacle)
            self.assertIn('altitude_msl', obstacle)
            self.assertIn('sphere_radius', obstacle)

    def test_access_logged(self):
        """Tests that access is logged."""
        response = self.client.get(obstacle_url)
        self.assertEqual(200, response.status_code)

        self.assertEqual(1, len(ObstacleAccessLog.objects.all()))

    def test_disable_log(self):
        """Normal users cannot disable logging."""
        response = self.client.get(obstacle_url, {'log': 'false'})
        self.assertEqual(response.status_code, 400)

    def test_loadtest(self):
        """Tests the max load the view can handle."""
        if not settings.TEST_ENABLE_LOADTEST:
            return

        total_ops = 0
        start_t = time.clock()
        while time.clock() - start_t < settings.TEST_LOADTEST_TIME:
            self.client.get(obstacle_url)
            total_ops += 1
        end_t = time.clock()
        total_t = end_t - start_t
        op_rate = total_ops / total_t

        print 'Obstacle Info Rate (%f)' % op_rate
        self.assertGreaterEqual(
                op_rate, settings.TEST_LOADTEST_INTEROP_MIN_RATE)


class TestObstaclesViewSuperuser(TestObstaclesView):
    """Tests the getObstacles view as superuser."""

    def setUp(self):
        super(TestObstaclesViewSuperuser, self).setUp()

        self.user = User.objects.create_superuser(
                'superuser', 'email@example.com', 'superpass')
        self.user.save()

        # Login
        response = self.client.post(login_url, {
            'username': 'superuser',
            'password': 'superpass'
        })
        self.assertEqual(200, response.status_code)

    def test_bad_param(self):
        """Non true/false doesn't work."""
        response = self.client.get(obstacle_url, {'log': '42'})
        self.assertEqual(400, response.status_code)

    def test_disable_log(self):
        """Superuser can disable logging."""
        response = self.client.get(obstacle_url, {'log': 'false'})
        self.assertEqual(200, response.status_code)

        self.assertEqual(0, len(ObstacleAccessLog.objects.all()))

    def test_enable_log(self):
        """Log stays enabled."""
        response = self.client.get(obstacle_url, {'log': 'true'})
        self.assertEqual(200, response.status_code)

        self.assertEqual(1, len(ObstacleAccessLog.objects.all()))
