  Project Prompt: Static Find Good Hikes

  1. Core Value Proposition:
  - Problem: The current Kubernetes-based find-good-hikes service requires persistent infrastructure, databases, and runtime weather processing, making it complex to operate and scale.
  - Solution: A purely static website that serves pre-computed hiking windows with client-side filtering, eliminating all server-side dependencies.
  - Value: Reduces operational complexity by 90%, eliminates persistent services, enables CDN caching, and provides instant user responses through pre-computed data.

  2. Intended Use Case:
  - Primary User: Weekend hikers who want to find good hiking opportunities with weather-based recommendations.
  - Scenario: User visits static website, enters location and preferences (fitness level, weather tolerance, available dates), and instantly sees filtered results from pre-computed hiking windows without any server processing.

  3. MVP Scope & Key Features:
  - CI/CD Data Pipeline:
    - Python script that fetches walk data and weather forecasts
    - Pre-computes all viable hiking windows (7-day forecast horizon)
    - Generates static JSON assets (index + individual walk files)
    - Runs in GitHub Actions every hour to refresh data
  - Static Website:
    - Single-page application with location input and filter controls
    - Client-side haversine distance calculation for location filtering
    - Prefetching of nearby walk assets for instant results
    - Pure JavaScript filtering of weather conditions and hike characteristics
  - Asset Structure:
    - index.json: All walks with filterable properties (coordinates, duration, distance, ascent) + asset references
    - walks/[uuid].json: Individual walk display data with viable weather windows
  - De-scoped for MVP: Real-time weather updates, server-side APIs, databases,  Kubernetes deployment, user authentication

  4. Technical Constraints & Considerations:
  - Stack: Python for CI data generation, vanilla JavaScript + HTML/CSS for static site, no frameworks or build tools required
  - Key Design Principle: "Pre-compute everything, filter client-side" - eliminate all runtime server processing by moving computation to build time
  - Data Retention: 7-day forecast horizon, rebuilt every hour via GitHub Actions
  - Performance: Index file <100KB, individual walk assets <1KB each, total static assets ~2MB
  - Previous implementation: @cluster/services/find-good-hikes

  5. Acceptance Criteria & Testing Plan:
  - Behavior 1: CI pipeline successfully generates current hiking data
    - Test: Verify pipeline runs without errors and produces valid JSON assets with recent weather windows
  - Behavior 2: User enters location and gets nearby hikes with weather filtering
    - Test: Verify client correctly calculates distances, fetches relevant assets, and filters by weather preferences
  - Behavior 3: System handles edge cases gracefully (no viable weather, remote locations)
    - Test: Verify graceful handling when no walks meet criteria or user location has no nearby hikes
  - Behavior 4: Assets prefetch efficiently for smooth user experience
    - Test: Verify nearby walk assets load quickly and results appear instantly after initial location input

  6. Call to Action: Implementation Strategy
  - Your Task: Implement the static hiking website described in this brief, transforming the existing Kubernetes service into a pure static site.
  - Process:
    a. Plan First: Propose the technical architecture showing the CI data pipeline, static asset
  structure, and client-side filtering logic. Do not write any implementation code yet.
    b. Await Approval: Present the plan for review. I will provide feedback or approve it.
    c. Execute Step-by-Step: Once approved, implement the Python data pipeline first, then the static website, focusing on eliminating all server-side complexity while preserving the full filtering capabilities.