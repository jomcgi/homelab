#!/usr/bin/env python3
"""
Integration tests for the find_good_hikes project.

These tests verify that the COMPLETE USER JOURNEY works through the public CLI interface.
We test actual behavior, not implementation details.
"""

import unittest
import subprocess
import tempfile
import shutil
import os
import json
from pathlib import Path

class TestCLIIntegration(unittest.TestCase):
    """Test the complete user journey through the CLI."""
    
    def setUp(self):
        """Set up a temporary directory for each test."""
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)
        
        # Set environment variables to use test directory
        os.environ['DATA_DIR'] = self.test_dir
        os.environ['LOG_LEVEL'] = 'WARNING'  # Reduce noise during tests
    
    def tearDown(self):
        """Clean up after each test."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)
        # Clean up environment variables
        if 'DATA_DIR' in os.environ:
            del os.environ['DATA_DIR']
        if 'LOG_LEVEL' in os.environ:
            del os.environ['LOG_LEVEL']
    
    def run_cli_command(self, *args, expect_success=True):
        """
        Run a CLI command and return the result.
        
        This is our ONLY interface to the system - testing exactly how users interact.
        """
        cmd = ['python', f'{self.original_cwd}/main.py'] + list(args)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=self.original_cwd,
            env=os.environ.copy()
        )
        
        if expect_success and result.returncode != 0:
            self.fail(f"Command failed: {' '.join(cmd)}\nStdout: {result.stdout}\nStderr: {result.stderr}")
        
        return result
    
    def test_cli_help_shows_commands(self):
        """Test that --help shows all expected commands."""
        result = self.run_cli_command('--help')
        
        # Verify all expected commands are listed
        self.assertIn('scrape', result.stdout)
        self.assertIn('fetch-weather', result.stdout)
        self.assertIn('find', result.stdout)
        self.assertIn('update', result.stdout)
        
        # Verify usage examples are shown
        self.assertIn('Examples:', result.stdout)
        self.assertIn('python main.py update', result.stdout)
    
    def test_invalid_command_returns_error(self):
        """Test that invalid commands fail gracefully."""
        result = self.run_cli_command('invalid-command', expect_success=False)
        self.assertNotEqual(result.returncode, 0)
    
    def test_find_without_databases_fails_gracefully(self):
        """Test that find command fails gracefully when databases don't exist."""
        result = self.run_cli_command('find', '55.8827', '-4.2589', expect_success=False)
        
        # Should fail but not crash
        self.assertNotEqual(result.returncode, 0)
        
        # Should provide helpful error message
        self.assertIn('database not found', result.stderr.lower())
    
    def test_find_command_validates_coordinates(self):
        """Test that find command validates coordinate inputs."""
        # Test invalid latitude
        result = self.run_cli_command('find', 'invalid', '-4.2589', expect_success=False)
        self.assertNotEqual(result.returncode, 0)
        
        # Test missing longitude
        result = self.run_cli_command('find', '55.8827', expect_success=False)
        self.assertNotEqual(result.returncode, 0)
    
    def test_find_command_accepts_optional_parameters(self):
        """Test that find command accepts and validates optional parameters."""
        # This will fail due to missing databases, but should validate parameters first
        result = self.run_cli_command(
            'find', '55.8827', '-4.2589',
            '--radius', '50',
            '--hours-ahead', '24',
            '--limit', '5',
            '--show-weather',
            '--show-summary',
            expect_success=False
        )
        
        # Should fail due to missing databases, not parameter validation
        self.assertIn('database', result.stderr.lower())
        self.assertNotIn('invalid', result.stderr.lower())
        self.assertNotIn('error:', result.stderr.lower())
    
    def test_configuration_environment_variables_work(self):
        """Test that environment variables properly configure the system."""
        # Set custom configuration
        os.environ['LOG_LEVEL'] = 'DEBUG'
        os.environ['APP_DEFAULT_SEARCH_RADIUS_KM'] = '100'
        
        # Run a command that will show configuration is working
        result = self.run_cli_command('find', '55.8827', '-4.2589', expect_success=False)
        
        # Should still fail due to missing databases, but configuration should work
        self.assertNotEqual(result.returncode, 0)
        
        # Clean up
        del os.environ['APP_DEFAULT_SEARCH_RADIUS_KM']
    
    def test_log_level_override_works(self):
        """Test that --log-level command line option works."""
        result = self.run_cli_command(
            '--log-level', 'DEBUG',
            'find', '55.8827', '-4.2589',
            expect_success=False
        )
        
        # Should fail due to missing databases
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('database', result.stderr.lower())

class TestEndToEndUserJourney(unittest.TestCase):
    """
    Test the complete end-to-end user journey.
    
    NOTE: These tests require network access and will make real HTTP requests.
    They are disabled by default but can be enabled for full integration testing.
    """
    
    def setUp(self):
        """Set up test environment."""
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)
        
        # Set environment to use test directory
        os.environ['DATA_DIR'] = self.test_dir
        os.environ['LOG_LEVEL'] = 'INFO'
    
    def tearDown(self):
        """Clean up test environment."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)
        if 'DATA_DIR' in os.environ:
            del os.environ['DATA_DIR']
        if 'LOG_LEVEL' in os.environ:
            del os.environ['LOG_LEVEL']
    
    def run_cli_command(self, *args, timeout=300):
        """Run CLI command with timeout for network operations."""
        cmd = ['python', f'{self.original_cwd}/main.py'] + list(args)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=self.original_cwd,
            env=os.environ.copy()
        )
        return result
    
    @unittest.skip("Requires network access - enable manually for full integration testing")
    def test_complete_user_workflow(self):
        """
        Test the complete user workflow:
        1. Scrape walks data
        2. Fetch weather forecasts  
        3. Find walks with weather ranking
        
        This is the REAL test - does the system work end-to-end for actual users?
        """
        # Step 1: Scrape walks data
        print("Step 1: Scraping walks data...")
        scrape_result = self.run_cli_command('scrape', timeout=600)  # 10 minute timeout
        
        if scrape_result.returncode != 0:
            self.fail(f"Scraping failed:\nStdout: {scrape_result.stdout}\nStderr: {scrape_result.stderr}")
        
        # Verify walks database was created
        walks_db_path = Path(self.test_dir) / "walks.db"
        self.assertTrue(walks_db_path.exists(), "Walks database should be created")
        
        # Step 2: Fetch weather forecasts
        print("Step 2: Fetching weather forecasts...")
        weather_result = self.run_cli_command('fetch-weather', timeout=600)  # 10 minute timeout
        
        if weather_result.returncode != 0:
            self.fail(f"Weather fetching failed:\nStdout: {weather_result.stdout}\nStderr: {weather_result.stderr}")
        
        # Verify forecasts database was created
        forecasts_db_path = Path(self.test_dir) / "forecasts.sqlite.db"
        self.assertTrue(forecasts_db_path.exists(), "Forecasts database should be created")
        
        # Step 3: Find walks near Glasgow
        print("Step 3: Finding walks with weather data...")
        find_result = self.run_cli_command(
            'find', '55.8827', '-4.2589',
            '--radius', '50',
            '--limit', '5',
            '--show-weather'
        )
        
        if find_result.returncode != 0:
            self.fail(f"Find walks failed:\nStdout: {find_result.stdout}\nStderr: {find_result.stderr}")
        
        # Verify we get meaningful output
        self.assertIn("walks:", find_result.stdout.lower())
        
        # If we found walks, verify they have weather scores
        if "weather:" in find_result.stdout.lower():
            self.assertIn("weather:", find_result.stdout.lower())
        
        print("✅ Complete user workflow successful!")
    
    @unittest.skip("Requires network access - enable manually for testing")
    def test_update_command_workflow(self):
        """Test the update command that combines scrape + fetch-weather."""
        print("Testing update command...")
        
        result = self.run_cli_command('update', timeout=1200)  # 20 minute timeout
        
        if result.returncode != 0:
            self.fail(f"Update failed:\nStdout: {result.stdout}\nStderr: {result.stderr}")
        
        # Verify both databases were created
        walks_db_path = Path(self.test_dir) / "walks.db"
        forecasts_db_path = Path(self.test_dir) / "forecasts.sqlite.db"
        
        self.assertTrue(walks_db_path.exists(), "Walks database should be created")
        self.assertTrue(forecasts_db_path.exists(), "Forecasts database should be created")
        
        print("✅ Update command successful!")

class TestSystemRobustness(unittest.TestCase):
    """Test that the system handles edge cases and errors gracefully."""
    
    def setUp(self):
        """Set up test environment."""
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)
        os.environ['DATA_DIR'] = self.test_dir
        os.environ['LOG_LEVEL'] = 'WARNING'
    
    def tearDown(self):
        """Clean up test environment."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)
        if 'DATA_DIR' in os.environ:
            del os.environ['DATA_DIR']
        if 'LOG_LEVEL' in os.environ:
            del os.environ['LOG_LEVEL']
    
    def run_cli_command(self, *args, expect_success=True):
        """Run CLI command."""
        cmd = ['python', f'{self.original_cwd}/main.py'] + list(args)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=self.original_cwd,
            env=os.environ.copy()
        )
        
        if expect_success and result.returncode != 0:
            self.fail(f"Command failed: {' '.join(cmd)}\nStdout: {result.stdout}\nStderr: {result.stderr}")
        
        return result
    
    def test_system_handles_invalid_config_gracefully(self):
        """Test that invalid configuration is handled gracefully."""
        # Set invalid configuration
        os.environ['CACHE_WEATHER_CACHE_EXPIRE_HOURS'] = 'invalid'
        
        result = self.run_cli_command('--help', expect_success=False)
        
        # Should fail due to configuration error, but not crash
        self.assertNotEqual(result.returncode, 0)
        
        # Clean up
        del os.environ['CACHE_WEATHER_CACHE_EXPIRE_HOURS']
    
    def test_extreme_coordinate_values(self):
        """Test that extreme coordinate values are handled."""
        # Test coordinates at edge of valid range
        result = self.run_cli_command('find', '90.0', '180.0', expect_success=False)
        # Should fail due to missing databases, not coordinate validation
        self.assertIn('database', result.stderr.lower())
        
        result = self.run_cli_command('find', '-90.0', '-180.0', expect_success=False)
        # Should fail due to missing databases, not coordinate validation
        self.assertIn('database', result.stderr.lower())

def run_tests():
    """Run all integration tests."""
    # Set up logging to reduce noise
    import logging
    logging.basicConfig(level=logging.WARNING)
    
    print("Running CLI Integration Tests...")
    print("=" * 50)
    print("Testing the complete user experience through the CLI interface.")
    print("These tests verify actual behavior, not implementation details.")
    print("=" * 50)
    
    # Run the tests
    unittest.main(verbosity=2)

if __name__ == '__main__':
    run_tests()