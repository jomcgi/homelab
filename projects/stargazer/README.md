# Stargazer

Finds the best stargazing spots in Scotland for the next 72 hours.

## Overview

Multi-phase pipeline: light pollution atlas + OSM road data to identify dark zones near roads, scored by weather forecast.

| Component   | Description                                                                   |
| ----------- | ----------------------------------------------------------------------------- |
| **backend** | Pipeline that combines light pollution data, OSM roads, and weather forecasts |
| **tests**   | Test suite for the scoring pipeline                                           |
