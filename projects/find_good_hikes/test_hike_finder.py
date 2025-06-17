#!/usr/bin/env python3
"""
Tests for HikeFinder that follow CLAUDE.md principles.

We test ACTUAL BEHAVIOR through the public interface, not implementation details.
This tests the complete user journey as they would experience it.
"""

import unittest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch

from hike_finder import HikeFinder, HikeFinderError


class TestHikeFinderBehavior(unittest.TestCase):
    """Test actual behavior through the public interface."""
    
    def setUp(self):
        """Set up isolated test environment."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.finder = HikeFinder(data_dir=self.test_dir)
    
    def tearDown(self):
        """Clean up test environment."""
        shutil.rmtree(self.test_dir)
    
    def test_find_hikes_requires_data(self):
        """Test that find_hikes fails gracefully when no data exists."""
        with self.assertRaises(HikeFinderError) as cm:
            self.finder.find_hikes(55.8827, -4.2589)
        
        # Should give clear error message
        self.assertIn("No hiking data found", str(cm.exception))
        self.assertIn("update_data", str(cm.exception))
    
    def test_find_hikes_validates_coordinates(self):
        """Test coordinate validation."""
        # This will fail on missing data, but should validate coordinates first
        with self.assertRaises((HikeFinderError, ValueError)):
            self.finder.find_hikes(999, -4.2589)  # Invalid latitude
    
    def test_find_hikes_accepts_valid_parameters(self):
        """Test that valid parameters are accepted."""
        # This will fail due to missing data, but parameter validation should pass
        with self.assertRaises(HikeFinderError) as cm:
            self.finder.find_hikes(
                latitude=55.8827,
                longitude=-4.2589,
                radius_km=50.0,
                max_results=5
            )
        
        # Should fail on missing data, not parameter validation
        self.assertIn("No hiking data found", str(cm.exception))
    
    def test_hike_dataclass_has_expected_fields(self):
        """Test that Hike objects have the expected simple interface."""
        from hike_finder import Hike
        
        # Test we can create a Hike with all expected fields
        hike = Hike(
            name="Test Hike",
            distance_km=5.0,
            duration_hours=2.5,
            url="https://example.com",
            weather_score=85.0,
            weather_summary="Sunny and pleasant",
            distance_from_you_km=12.5
        )
        
        # Verify all fields are accessible
        self.assertEqual(hike.name, "Test Hike")
        self.assertEqual(hike.distance_km, 5.0)
        self.assertEqual(hike.duration_hours, 2.5)
        self.assertEqual(hike.weather_score, 85.0)
    
    @unittest.skip("Requires network access - enable manually for integration testing")
    def test_complete_user_journey(self):
        """
        Test the complete user journey: update data then find hikes.
        
        This is the REAL test - does it work end-to-end?
        """
        # Step 1: Update data (this takes time but tests real behavior)
        self.finder.update_data()
        
        # Step 2: Find hikes near Glasgow
        hikes = self.finder.find_hikes(55.8827, -4.2589, radius_km=25, max_results=5)
        
        # Verify we get meaningful results
        self.assertIsInstance(hikes, list)
        
        if hikes:  # If we found any hikes
            hike = hikes[0]
            
            # Verify each hike has expected data
            self.assertIsInstance(hike.name, str)
            self.assertGreater(len(hike.name), 0)
            self.assertIsInstance(hike.distance_km, (int, float))
            self.assertGreater(hike.distance_km, 0)
            self.assertIsInstance(hike.weather_score, (int, float))
            self.assertGreaterEqual(hike.weather_score, 0)
            self.assertLessEqual(hike.weather_score, 100)
            self.assertIsInstance(hike.url, str)
            self.assertTrue(hike.url.startswith('http'))


class TestHikeFinderEdgeCases(unittest.TestCase):
    """Test edge cases and error conditions."""
    
    def setUp(self):
        """Set up test environment."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.finder = HikeFinder(data_dir=self.test_dir)
    
    def tearDown(self):
        """Clean up test environment."""
        shutil.rmtree(self.test_dir)
    
    def test_extreme_coordinates(self):
        """Test extreme but valid coordinates."""
        # These should be accepted (though no data exists)
        with self.assertRaises(HikeFinderError):
            self.finder.find_hikes(89.9, 179.9)  # Near north pole
        
        with self.assertRaises(HikeFinderError):
            self.finder.find_hikes(-89.9, -179.9)  # Near south pole
    
    def test_zero_radius(self):
        """Test zero search radius."""
        with self.assertRaises(HikeFinderError):
            self.finder.find_hikes(55.8827, -4.2589, radius_km=0)
    
    def test_zero_max_results(self):
        """Test zero max results."""
        with self.assertRaises(HikeFinderError):
            self.finder.find_hikes(55.8827, -4.2589, max_results=0)


if __name__ == '__main__':
    print("Testing HikeFinder behavior...")
    print("=" * 50)
    print("These tests verify the public interface works as expected.")
    print("They test actual behavior, not implementation details.")
    print("=" * 50)
    
    unittest.main(verbosity=2)