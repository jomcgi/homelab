"""
Weather scoring algorithm for ranking walks based on weather conditions.

This module provides functionality to score weather forecasts for hiking,
considering factors like precipitation, temperature, wind, and cloud cover.
"""

import logging
from typing import List, Optional
from datetime import datetime, timedelta
from hourly_forecast import HourlyForecast

logger = logging.getLogger(__name__)

class WeatherScore:
    """Container for weather score and explanation."""
    
    def __init__(self, score: float, explanation: str, factors: dict):
        self.score = score  # 0-100, higher is better
        self.explanation = explanation
        self.factors = factors  # Breakdown of scoring factors
    
    def __str__(self):
        return f"Weather Score: {self.score:.1f}/100 - {self.explanation}"

def score_temperature(temp_celsius: Optional[float]) -> tuple[float, str]:
    """
    Score temperature for hiking comfort.
    
    Optimal hiking temperature is 10-20°C.
    Returns score (0-1) and explanation.
    """
    if temp_celsius is None:
        return 0.5, "Unknown temperature"
    
    if 10 <= temp_celsius <= 20:
        return 1.0, f"Perfect hiking temperature ({temp_celsius}°C)"
    elif 5 <= temp_celsius < 10:
        return 0.8, f"Cool but comfortable ({temp_celsius}°C)"
    elif 20 < temp_celsius <= 25:
        return 0.8, f"Warm but manageable ({temp_celsius}°C)"
    elif 0 <= temp_celsius < 5:
        return 0.6, f"Cold ({temp_celsius}°C)"
    elif 25 < temp_celsius <= 30:
        return 0.6, f"Hot ({temp_celsius}°C)"
    elif temp_celsius < 0:
        return 0.3, f"Freezing ({temp_celsius}°C)"
    else:  # > 30°C
        return 0.2, f"Too hot for comfortable hiking ({temp_celsius}°C)"

def score_precipitation(precip_mm: Optional[float]) -> tuple[float, str]:
    """
    Score precipitation for hiking conditions.
    
    Any significant rain makes hiking unpleasant.
    Returns score (0-1) and explanation.
    """
    if precip_mm is None:
        return 0.8, "No precipitation data"
    
    if precip_mm == 0:
        return 1.0, "No rain"
    elif precip_mm <= 0.5:
        return 0.9, f"Light drizzle ({precip_mm}mm)"
    elif precip_mm <= 2.0:
        return 0.6, f"Light rain ({precip_mm}mm)"
    elif precip_mm <= 5.0:
        return 0.3, f"Moderate rain ({precip_mm}mm)"
    else:
        return 0.1, f"Heavy rain ({precip_mm}mm)"

def score_wind(wind_speed_ms: Optional[float]) -> tuple[float, str]:
    """
    Score wind speed for hiking safety and comfort.
    
    Strong winds can be dangerous on exposed ridges.
    Returns score (0-1) and explanation.
    """
    if wind_speed_ms is None:
        return 0.7, "No wind data"
    
    # Convert m/s to km/h for easier understanding
    wind_kmh = wind_speed_ms * 3.6
    
    if wind_kmh <= 10:
        return 1.0, f"Calm ({wind_kmh:.1f} km/h)"
    elif wind_kmh <= 20:
        return 0.9, f"Light breeze ({wind_kmh:.1f} km/h)"
    elif wind_kmh <= 35:
        return 0.7, f"Moderate wind ({wind_kmh:.1f} km/h)"
    elif wind_kmh <= 50:
        return 0.4, f"Strong wind ({wind_kmh:.1f} km/h)"
    else:
        return 0.1, f"Very strong wind ({wind_kmh:.1f} km/h)"

def score_cloud_cover(cloud_fraction: Optional[float]) -> tuple[float, str]:
    """
    Score cloud cover for hiking enjoyment.
    
    Some clouds are nice for photos, but overcast reduces visibility.
    Returns score (0-1) and explanation.
    """
    if cloud_fraction is None:
        return 0.7, "No cloud data"
    
    cloud_percent = cloud_fraction * 100
    
    if cloud_percent <= 25:
        return 1.0, f"Clear skies ({cloud_percent:.0f}% clouds)"
    elif cloud_percent <= 50:
        return 0.9, f"Partly cloudy ({cloud_percent:.0f}% clouds)"
    elif cloud_percent <= 75:
        return 0.7, f"Mostly cloudy ({cloud_percent:.0f}% clouds)"
    else:
        return 0.5, f"Overcast ({cloud_percent:.0f}% clouds)"

def score_visibility_conditions(symbol_code: Optional[str]) -> tuple[float, str]:
    """
    Score weather symbol for visibility and general conditions.
    
    Based on met.no weather symbols. Night symbols are converted to day equivalents
    since we only consider daylight hours for hiking.
    Returns score (0-1) and explanation.
    """
    if symbol_code is None:
        return 0.7, "No weather symbol"
    
    # Convert night symbols to day equivalents for hiking context
    if symbol_code.endswith('_night'):
        symbol_code = symbol_code.replace('_night', '_day')
    
    # Map weather symbols to scores
    symbol_scores = {
        'clearsky_day': (1.0, "Clear sunny weather"),
        'fair_day': (0.95, "Fair weather"),
        'partlycloudy_day': (0.85, "Partly cloudy"),
        'cloudy': (0.7, "Cloudy"),
        'fog': (0.4, "Foggy conditions"),
        'lightrainshowers_day': (0.5, "Light rain showers"),
        'rainshowers_day': (0.3, "Rain showers"),
        'heavyrainshowers_day': (0.1, "Heavy rain showers"),
        'lightrain': (0.4, "Light rain"),
        'rain': (0.2, "Rain"),
        'heavyrain': (0.05, "Heavy rain"),
        'lightsnow': (0.3, "Light snow"),
        'snow': (0.2, "Snow"),
        'heavysnow': (0.1, "Heavy snow"),
        'sleet': (0.15, "Sleet"),
        'thunderstorm': (0.05, "Thunderstorm"),
    }
    
    return symbol_scores.get(symbol_code, (0.5, f"Unknown conditions ({symbol_code})"))

def find_good_weather_windows(forecasts: List[HourlyForecast], min_duration_hours: float = 2.0, min_score: float = 70.0) -> List[tuple]:
    """
    Find continuous windows of good weather suitable for hiking.
    
    Args:
        forecasts: List of hourly forecasts
        min_duration_hours: Minimum duration of good weather needed
        min_score: Minimum weather score threshold (0-100)
    
    Returns:
        List of tuples (start_time, end_time, avg_score) for good weather windows
    """
    if not forecasts:
        return []
    
    good_windows = []
    current_window_start = None
    current_window_forecasts = []
    
    for forecast in forecasts:
        score = score_forecast(forecast)
        
        if score.score >= min_score:
            # Good weather - start or continue window
            if current_window_start is None:
                current_window_start = forecast.time
                current_window_forecasts = [forecast]
            else:
                # Check if we're crossing into a new day - if so, end current window and start new one
                if forecast.time.date() != current_window_forecasts[-1].time.date():
                    # End current window first
                    if current_window_forecasts:
                        window_duration = len(current_window_forecasts)
                        if window_duration >= min_duration_hours:
                            end_time = current_window_start + timedelta(hours=window_duration)
                            avg_score = sum(score_forecast(f).score for f in current_window_forecasts) / len(current_window_forecasts)
                            good_windows.append((current_window_start, end_time, avg_score))
                    
                    # Start new window
                    current_window_start = forecast.time
                    current_window_forecasts = [forecast]
                else:
                    # Same day, continue window
                    current_window_forecasts.append(forecast)
        else:
            # Bad weather - end current window if it exists
            if current_window_start is not None and current_window_forecasts:
                window_duration = len(current_window_forecasts)
                if window_duration >= min_duration_hours:
                    end_time = current_window_start + timedelta(hours=window_duration)
                    avg_score = sum(score_forecast(f).score for f in current_window_forecasts) / len(current_window_forecasts)
                    good_windows.append((current_window_start, end_time, avg_score))
                
                current_window_start = None
                current_window_forecasts = []
    
    # Handle case where good weather continues to the end
    if current_window_start is not None and current_window_forecasts:
        window_duration = len(current_window_forecasts)
        if window_duration >= min_duration_hours:
            end_time = current_window_start + timedelta(hours=window_duration)
            avg_score = sum(score_forecast(f).score for f in current_window_forecasts) / len(current_window_forecasts)
            good_windows.append((current_window_start, end_time, avg_score))
    
    return good_windows

def find_optimal_window_for_duration(forecasts: List[HourlyForecast], duration_hours: float) -> tuple:
    """
    Find the optimal time window of specific duration with the best weather.
    
    Args:
        forecasts: List of hourly forecasts (should be daylight hours only)
        duration_hours: Required duration for the activity
    
    Returns:
        Tuple of (start_time, end_time, avg_score) for the best window, or None if no suitable window
    """
    if not forecasts or duration_hours <= 0:
        return None
    
    # Convert duration to number of hours (round up to ensure we have enough time)
    duration_hours_int = int(duration_hours + 0.99)  # Round up
    
    if len(forecasts) < duration_hours_int:
        return None
    
    best_window = None
    best_score = 0
    
    # Slide a window of the required duration across all forecasts
    for i in range(len(forecasts) - duration_hours_int + 1):
        window_forecasts = forecasts[i:i + duration_hours_int]
        
        # Check if window spans multiple days - skip if it does (for daytime hiking)
        start_date = window_forecasts[0].time.date()
        end_date = window_forecasts[-1].time.date()
        if start_date != end_date:
            continue  # Skip windows that span midnight
        
        # Calculate average score for this window
        window_scores = [score_forecast(f).score for f in window_forecasts]
        avg_score = sum(window_scores) / len(window_scores)
        
        if avg_score > best_score:
            best_score = avg_score
            start_time = window_forecasts[0].time
            end_time = start_time + timedelta(hours=duration_hours)
            best_window = (start_time, end_time, avg_score)
    
    return best_window

def find_good_windows_for_duration(forecasts: List[HourlyForecast], duration_hours: float, min_score: float = 50.0) -> List[tuple]:
    """
    Find all good time windows of specific duration that meet the minimum score threshold.
    
    Args:
        forecasts: List of hourly forecasts (should be daylight hours only)
        duration_hours: Required duration for the activity
        min_score: Minimum weather score threshold (0-100)
    
    Returns:
        List of tuples (start_time, end_time, avg_score) for good windows, sorted by score descending
    """
    if not forecasts or duration_hours <= 0:
        return []
    
    # Convert duration to number of hours (round up to ensure we have enough time)
    duration_hours_int = int(duration_hours + 0.99)  # Round up
    
    if len(forecasts) < duration_hours_int:
        return []
    
    good_windows = []
    
    # Slide a window of the required duration across all forecasts
    for i in range(len(forecasts) - duration_hours_int + 1):
        window_forecasts = forecasts[i:i + duration_hours_int]
        
        # Check if window spans multiple days - skip if it does (for daytime hiking)
        start_date = window_forecasts[0].time.date()
        end_date = window_forecasts[-1].time.date()
        if start_date != end_date:
            continue  # Skip windows that span midnight
        
        # Calculate average score for this window
        window_scores = [score_forecast(f).score for f in window_forecasts]
        avg_score = sum(window_scores) / len(window_scores)
        
        # Only include windows that meet the minimum score threshold
        if avg_score >= min_score:
            start_time = window_forecasts[0].time
            end_time = start_time + timedelta(hours=duration_hours)
            good_windows.append((start_time, end_time, avg_score))
    
    # Sort by score descending (best windows first)
    good_windows.sort(key=lambda w: w[2], reverse=True)
    
    return good_windows

def score_forecast(forecast: HourlyForecast) -> WeatherScore:
    """
    Score a single weather forecast for hiking suitability.
    
    Combines multiple weather factors into an overall score.
    """
    # Score individual factors
    temp_score, temp_desc = score_temperature(forecast.air_temperature)
    precip_score, precip_desc = score_precipitation(forecast.precipitation_amount)
    wind_score, wind_desc = score_wind(forecast.wind_speed)
    cloud_score, cloud_desc = score_cloud_cover(forecast.cloud_area_fraction)
    symbol_score, symbol_desc = score_visibility_conditions(forecast.symbol_code)
    
    # Weight the factors (precipitation and temperature are most important)
    weights = {
        'precipitation': 0.35,  # Most important - rain ruins hiking
        'temperature': 0.25,    # Very important for comfort
        'wind': 0.20,          # Important for safety
        'visibility': 0.15,     # Weather symbol gives overall picture
        'clouds': 0.05,        # Least important factor
    }
    
    # Calculate weighted score
    weighted_score = (
        precip_score * weights['precipitation'] +
        temp_score * weights['temperature'] +
        wind_score * weights['wind'] +
        symbol_score * weights['visibility'] +
        cloud_score * weights['clouds']
    ) * 100  # Convert to 0-100 scale
    
    # Generate explanation
    factors = [precip_desc, temp_desc, wind_desc, symbol_desc]
    explanation = f"{symbol_desc}. {temp_desc}. {precip_desc}. {wind_desc}."
    
    factor_breakdown = {
        'precipitation': (precip_score, precip_desc),
        'temperature': (temp_score, temp_desc),
        'wind': (wind_score, wind_desc),
        'visibility': (symbol_score, symbol_desc),
        'clouds': (cloud_score, cloud_desc),
    }
    
    return WeatherScore(
        score=weighted_score,
        explanation=explanation,
        factors=factor_breakdown
    )

def score_forecast_period(forecasts: List[HourlyForecast], hours_ahead: int = 24, walk_duration_hours: float = None) -> WeatherScore:
    """
    Score a period of weather forecasts for hiking planning.
    
    Args:
        forecasts: List of hourly forecasts
        hours_ahead: How many hours ahead to consider
        walk_duration_hours: Expected duration of the walk in hours
    
    Returns:
        Overall weather score for the period
    """
    if not forecasts:
        return WeatherScore(0, "No weather data available", {})
    
    # Filter to the specified time period (daylight filtering already done in find_walks.py)
    now = datetime.now(forecasts[0].time.tzinfo)
    cutoff_time = now + timedelta(hours=hours_ahead)
    
    relevant_forecasts = [
        f for f in forecasts
        if f.time >= now and f.time <= cutoff_time
    ]
    
    if not relevant_forecasts:
        return WeatherScore(0, "No forecasts available for the specified period", {})
    
    # Score each forecast
    scores = [score_forecast(f) for f in relevant_forecasts]
    
    # Calculate average score (weighted by time - closer forecasts matter more)
    total_weight = 0
    weighted_sum = 0
    
    for i, score in enumerate(scores):
        # Weight decreases with time (first hour gets weight 1.0, later hours get less)
        weight = 1.0 / (1 + i * 0.1)
        weighted_sum += score.score * weight
        total_weight += weight
    
    avg_score = weighted_sum / total_weight if total_weight > 0 else 0
    
    # Find best and worst periods
    best_score = max(scores, key=lambda s: s.score)
    worst_score = min(scores, key=lambda s: s.score)
    
    # Find optimal window for specific walk duration
    days_ahead = hours_ahead // 24
    explanation_parts = [f"Next {days_ahead} days forecast."]
    optimal_window = None
    
    if walk_duration_hours and relevant_forecasts:
        # Find multiple good windows of exactly the required duration
        good_windows = find_good_windows_for_duration(relevant_forecasts, walk_duration_hours, min_score=50.0)
        if good_windows:
            optimal_window = good_windows[0]  # Best window for backward compatibility
            start_time, end_time, window_score = optimal_window
            # Format with date if not today
            today = datetime.now(start_time.tzinfo).date()
            start_date = start_time.date()
            
            if start_date == today:
                date_str = "Today"
            elif start_date == today + timedelta(days=1):
                date_str = "Tomorrow"
            else:
                date_str = start_time.strftime('%a %d/%m')
            
            explanation_parts.append(f"Best {walk_duration_hours:.1f}h slot: {date_str} {start_time.strftime('%H:%M')}-{end_time.strftime('%H:%M')} (score {window_score:.0f}/100).")
        else:
            explanation_parts.append(f"No suitable {walk_duration_hours:.1f}h window found.")
            optimal_window = None
            good_windows = []
    else:
        # Fall back to general good weather windows analysis
        min_duration = 2.0
        good_windows = find_good_weather_windows(relevant_forecasts, min_duration_hours=min_duration, min_score=70.0)
        if good_windows:
            best_window = max(good_windows, key=lambda w: w[2])
            duration_hours = (best_window[1] - best_window[0]).total_seconds() / 3600
            
            # Format with date if not today
            today = datetime.now(best_window[0].tzinfo).date()
            start_date = best_window[0].date()
            
            if start_date == today:
                date_str = "Today"
            elif start_date == today + timedelta(days=1):
                date_str = "Tomorrow"
            else:
                date_str = best_window[0].strftime('%a %d/%m')
            
            explanation_parts.append(f"Best window: {date_str} {best_window[0].strftime('%H:%M')}-{best_window[1].strftime('%H:%M')} ({duration_hours:.1f}h, score {best_window[2]:.0f}/100).")
        else:
            explanation_parts.append("No extended good weather periods found.")
    
    explanation_parts.append(f"Peak conditions: {best_score.explanation[:40]}...")
    explanation = " ".join(explanation_parts)
    
    # Extract weather details from all good windows for structured data
    weather_details = None
    weather_windows = []
    
    if 'good_windows' in locals() and good_windows:
        # Create detailed weather info for each good window
        for window_start, window_end, window_score in good_windows:
            window_forecasts = [f for f in relevant_forecasts 
                              if window_start <= f.time <= window_end]
            
            if window_forecasts:
                # Get representative forecast from middle of window
                mid_forecast = window_forecasts[len(window_forecasts)//2]
                # Handle cloud cover - if it's already > 1, assume it's in percentage, otherwise convert from fraction
                cloud_fraction = mid_forecast.cloud_area_fraction or 0
                cloud_percent = cloud_fraction * 100 if cloud_fraction <= 1.0 else cloud_fraction
                cloud_percent = min(100, max(0, cloud_percent))  # Clamp to 0-100%
                
                window_detail = {
                    'temperature_c': mid_forecast.air_temperature,
                    'precipitation_mm': mid_forecast.precipitation_amount or 0,
                    'wind_speed_kmh': (mid_forecast.wind_speed or 0) * 3.6,
                    'cloud_cover_percent': cloud_percent,
                    'start_time': window_start,
                    'end_time': window_end,
                    'duration_hours': walk_duration_hours or ((window_end - window_start).total_seconds() / 3600),
                    'score': window_score
                }
                weather_windows.append(window_detail)
        
        # Keep backward compatibility - weather_details is the best window
        if weather_windows:
            weather_details = weather_windows[0].copy()
            # Remove score from the main weather_details for backward compatibility
            weather_details.pop('score', None)
    elif relevant_forecasts:
        # No optimal window, use first forecast as fallback
        first_forecast = relevant_forecasts[0]
        # Handle cloud cover - if it's already > 1, assume it's in percentage, otherwise convert from fraction
        cloud_fraction = first_forecast.cloud_area_fraction or 0
        cloud_percent = cloud_fraction * 100 if cloud_fraction <= 1.0 else cloud_fraction
        cloud_percent = min(100, max(0, cloud_percent))  # Clamp to 0-100%
        
        weather_details = {
            'temperature_c': first_forecast.air_temperature,
            'precipitation_mm': first_forecast.precipitation_amount or 0,
            'wind_speed_kmh': (first_forecast.wind_speed or 0) * 3.6,
            'cloud_cover_percent': cloud_percent,
            'start_time': None,
            'end_time': None,
            'duration_hours': None
        }

    return WeatherScore(
        score=avg_score,
        explanation=explanation,
        factors={
            'best_period': best_score.factors,
            'worst_period': worst_score.factors,
            'num_forecasts': len(relevant_forecasts),
            'walk_duration_hours': walk_duration_hours,
            'optimal_window': optimal_window,
            'weather_details': weather_details,
            'weather_windows': weather_windows
        }
    )

def rank_walks_by_weather(walks_with_forecasts: List, hours_ahead: int = 24) -> List:
    """
    Rank walks by their weather scores.
    
    Args:
        walks_with_forecasts: List of WalkSearchResult objects with forecast data
        hours_ahead: How many hours ahead to consider for scoring
    
    Returns:
        List of walks sorted by weather score (best first)
    """
    scored_walks = []
    
    for walk in walks_with_forecasts:
        if walk.forecast:
            # Use the walk's duration for weather window analysis
            weather_score = score_forecast_period(walk.forecast, hours_ahead, walk.duration_h)
            walk.weather_score = weather_score
            scored_walks.append(walk)
        else:
            # No forecast data - give it a low score
            walk.weather_score = WeatherScore(0, "No weather data available", {})
            scored_walks.append(walk)
    
    # Sort by weather score (descending - best weather first)
    scored_walks.sort(key=lambda w: w.weather_score.score, reverse=True)
    
    logger.info(f"Ranked {len(scored_walks)} walks by weather conditions")
    for i, walk in enumerate(scored_walks[:5]):  # Log top 5
        logger.debug(f"{i+1}. {walk.name}: {walk.weather_score}")
    
    return scored_walks