Feature: Hike Finder API
  As a user
  I want to find good hiking routes via API
  So that I can integrate hiking data into other applications

  Background:
    Given the API server is running
    And the hike finder has sample data

  Scenario: Health check endpoint works
    When I request the health check endpoint
    Then I should get a healthy response

  Scenario: Check data status when no data exists
    Given there is no hiking data
    When I check the data status
    Then the status should be "no_data"
    And the message should mention missing data

  Scenario: Successfully find hikes near Edinburgh
    Given there are hiking routes in the database
    And there is weather forecast data
    When I search for hikes near Edinburgh with coordinates
    Then I should get a list of hikes
    And each hike should have weather information
    And the hikes should be sorted by weather score

  Scenario: Handle invalid coordinates
    When I search for hikes with invalid coordinates
    Then I should get a validation error

  Scenario: Handle large search radius
    When I search for hikes with too large radius
    Then I should get a validation error

  Scenario: Start data update in background
    When I request a data update
    Then the update should start in the background
    And I should get an accepted response

  Scenario: Find hikes returns empty when no matches
    Given there are hiking routes in the database
    When I search for hikes in Antarctica
    Then I should get an empty list of hikes
    And the total found should be 0