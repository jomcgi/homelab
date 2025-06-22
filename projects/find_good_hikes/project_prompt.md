  Project Prompt: Simplified Good Hikes - Batch Processing System

  1. Core Value Proposition:
  - Problem: The current Good Hikes system has ~4,000 lines of complex real-time processing code,
  multiple interfaces (CLI, web, API), and runtime weather calculations that add unnecessary
  complexity.
  - Solution: A simplified batch processing system that pre-computes all good hiking windows and
  serves them through a single, simple web interface.
  - Value: Reduces system complexity by 60-70%, eliminates runtime weather processing, and provides
  faster user responses through pre-computed data.

  2. Intended Use Case:
  - Primary User: Weekend hikers who want to find good hiking opportunities with weather-based
  recommendations.
  - Scenario: User visits simple web interface, applies filters (fitness level, weather tolerance,
  distance), sees pre-computed ranked list of hikes with specific time windows like "Ben Lomond:
  Wednesday 9am-3pm (12°C, 0mm rain, 15km/h wind, 30% cloud)".

  3. MVP Scope & Key Features:
  - Batch Processing System:
    - Hourly job that fetches weather data and pre-computes good hiking windows
    - Stores only windows that meet minimum quality thresholds (exclude extreme weather)
    - Pre-computes scores and weather characteristics (mm rain, km/h wind, % cloud cover)
  - Simple Web Interface:
    - Single page with filter form (distance, fitness level, weather tolerance)
    - Query pre-computed windows based on user location and preferences
    - Display ranked results with time windows and weather characteristics
  - Simplified Data Model:
    - Single table: good_windows with hike details, time window, weather characteristics, and
  pre-computed scores
  - De-scoped for MVP: CLI interface, real-time APIs, complex caching, runtime weather processing,
  multiple databases

  4. Technical Constraints & Considerations:
  - Stack: Python with minimal dependencies - Flask/FastAPI for web interface, SQLite for
  pre-computed data
  - Key Design Principle: "Batch processing over real-time complexity" - eliminate runtime weather
  calculations, API calls, and complex scoring
  - Data Retention: 7-day forecast horizon, rebuilt every hour via CI/batch job

  5. Acceptance Criteria & Testing Plan:
  - Behavior 1: Batch job successfully pre-computes good hiking windows
    - Test: Verify job runs without errors and populates database with reasonable time windows
  - Behavior 2: User applies filters and gets relevant hiking recommendations
    - Test: Verify filtering works correctly and returns only windows matching user criteria
  - Behavior 3: System handles periods with no good weather conditions
    - Test: Verify graceful handling when no windows meet quality thresholds

  6. Call to Action: Implementation Strategy
  - Your Task: Simplify the current Good Hikes system by implementing the batch processing
  architecture described above.
  - Process:
    a. Plan First: Propose a simplified architecture showing what to eliminate from the current
  ~4,000 line codebase and what the new simplified system looks like
    b. Await Approval: Present the plan for review before making changes
    c. Execute Step-by-Step: Implement batch processing first, then simplified web interface,
  focusing on eliminating complexity rather than adding features