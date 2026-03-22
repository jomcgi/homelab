import logging
import re
import uuid
from datetime import timedelta
from urllib.parse import urljoin

import requests  # nosemgrep: no-requests
import requests_cache  # nosemgrep: no-requests
from bs4 import BeautifulSoup
from projects.hikes.scrape_walkhighlands.error_handling import (
    ErrorCollector,
    handle_network_errors,
    log_performance,
    retry_on_failure,
)
from pydantic import BaseModel, ConfigDict, ValidationError
from pydantic_extra_types.coordinate import Coordinate
from pydantic_sqlite import DataBase
from timelength import TimeLength

# Configure logging
logger = logging.getLogger(__name__)


@retry_on_failure(max_retries=3, exceptions=(requests.RequestException,))
@handle_network_errors
@log_performance
def scrape_area_links_from_homepage(
    base_url: str,
    headers: dict,
    session: requests.Session,
) -> list[str]:
    extracted_links = []

    try:
        # Send HTTP GET request

        response = session.get(base_url, headers=headers, timeout=15)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        logger.debug(f"Successfully fetched page: {base_url}")

        # Parse the HTML content
        soup = BeautifulSoup(response.content, "html.parser")

        # Find the specific container div
        choose_area_div = soup.find("div", id="choosearea")

        if not choose_area_div:
            logger.warning("Could not find the <div id='choosearea'> container")
            return extracted_links  # Return empty list

        logger.debug("Found <div id='choosearea'>. Searching for links...")

        # Find all 'a' (anchor) tags within 'td' elements with class 'cell'
        # inside the 'choose_area_div'
        # This is more specific than just finding all 'a' tags in the div
        link_elements = choose_area_div.select("td.cell a")

        if not link_elements:
            logger.warning(
                "No links found matching the selector 'td.cell a' within #choosearea"
            )
            return extracted_links  # Return empty list

        logger.debug(f"Found {len(link_elements)} potential area links")

        # Extract href and text for each link
        for link in link_elements:
            href = link.get("href")
            # Get text and strip leading/trailing whitespace
            name = link.get_text(strip=True)

            if href and name:
                # Construct the absolute URL using urljoin
                absolute_href = urljoin(base_url, href)
                if ".shtml" in absolute_href or ".php" in absolute_href:
                    continue
                extracted_links.append(absolute_href)

            else:
                logger.debug(f"Found a link tag without href or text: {link}")

    except requests.exceptions.RequestException as e:
        logger.error(f"Request error for {base_url}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")

    return extracted_links


@retry_on_failure(max_retries=3, exceptions=(requests.RequestException,))
@handle_network_errors
@log_performance
def scrape_sub_area_links_from_area(
    base_url: str,
    headers: dict,
    session: requests.Session,
) -> list[str]:
    extracted_links = []

    try:
        # Send HTTP GET request

        response = session.get(base_url, headers=headers, timeout=15)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        print("Successfully fetched the page.")

        # Parse the HTML content
        soup = BeautifulSoup(response.content, "html.parser")

        # Find the specific container div
        choose_area_div = soup.find("div", id="arealist")

        if not choose_area_div:
            print("Error: Could not find the <div id='choosearea'> container.")
            return extracted_links  # Return empty list

        print("Found <div id='choosearea'>. Searching for links...")

        # Find all 'a' (anchor) tags within 'td' elements with class 'cell'
        # inside the 'choose_area_div'
        # This is more specific than just finding all 'a' tags in the div
        link_elements = choose_area_div.select("td.cell a")

        if not link_elements:
            logger.warning(
                "No links found matching the selector 'td.cell a' within #choosearea"
            )
            return extracted_links  # Return empty list

        logger.debug(f"Found {len(link_elements)} potential area links")

        # Extract href and text for each link
        for link in link_elements:
            href = link.get("href")
            # Get text and strip leading/trailing whitespace
            name = link.get_text(strip=True)

            if href and name:
                # Construct the absolute URL using urljoin
                absolute_href = urljoin(base_url, href)
                if ".php" in absolute_href:
                    continue
                extracted_links.append(absolute_href)

            else:
                logger.debug(f"Found a link tag without href or text: {link}")

    except requests.exceptions.RequestException as e:
        print(f"Error during requests to {base_url}: {e}")
    except Exception as e:
        logger.exception("Unexpected error during scraping of %s", base_url)
        print(f"An unexpected error occurred: {e}")

    return extracted_links


@retry_on_failure(max_retries=3, exceptions=(requests.RequestException,))
@handle_network_errors
@log_performance
def scrape_walks_from_sub_area(
    base_url: str,
    headers: dict,
    session: requests.Session,
) -> list[str]:
    extracted_links = []
    print(f"Scraping: {base_url}")
    try:
        # Send HTTP GET request

        response = session.get(base_url, headers=headers, timeout=15)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        print("Successfully fetched the page.")

        # Parse the HTML content
        soup = BeautifulSoup(response.content, "html.parser")

        # --- CORRECTED SELECTION ---
        # Select directly from the soup object, targeting the table inside the 'walktable' div.
        # If you want ALL walk links (first cell of each row):
        selector = "div.walktable > table.table1 > tbody > tr > td:nth-child(1) > a"
        # If you *really* only want the link from the very first row:
        # selector = 'div.walktable > table.table1 > tbody > tr:nth-child(1) > td:nth-child(1) > a'

        print(f"Using selector: {selector}")
        link_elements = soup.select(selector)
        # --- END CORRECTION ---

        if not link_elements:
            # Add more debugging here if it still fails
            print("Warning: No link elements found with the specified selector.")
            # You could try finding the walktable div to see if IT exists
            walk_table_div = soup.select_one("div.walktable")
            if walk_table_div:
                print("Found 'div.walktable', but the selector within it failed.")
                # print(walk_table_div.prettify()) # Uncomment to see its structure
            else:
                print(
                    "Error: Could not find the <div class='walktable'> container either."
                )
            return extracted_links  # Return empty list

        print(f"Found {len(link_elements)} walk links.")

        # Extract href and text for each link
        for link in link_elements:
            href = link.get("href")
            # Get text and strip leading/trailing whitespace
            name = link.get_text(strip=True)

            if href and name:
                # Construct the absolute URL using urljoin
                absolute_href = urljoin(base_url, href)
                # Optional: Skip links containing .php if they aren't walk details
                # if ".php" in absolute_href or "#" in absolute_href:
                #    continue
                print(f"  -> Adding: {absolute_href} ({name})")
                extracted_links.append(absolute_href)
            else:
                logger.debug(f"Found a link tag without href or text: {link}")

    except requests.exceptions.RequestException as e:
        print(f"Error during requests to {base_url}: {e}")
    except Exception as e:
        logger.exception("Unexpected error during scraping of %s", base_url)
        print(f"An unexpected error occurred: {e}")

    return extracted_links


class Walk(BaseModel):
    uuid: str
    name: str
    url: str
    distance_km: float
    ascent_m: int
    duration_h: float
    summary: str
    latitude: float
    longitude: float
    viable_dates: list[str] | None = None  # Pre-computed viable hiking dates

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
    )


def parse_duration(time_str: str) -> timedelta | None:
    """Parses duration strings like '5.5 - 6.5 hours' or '3 hours' into a timedelta."""
    if not time_str:
        return None
    try:
        # Remove "hours" and strip whitespace
        time_str = time_str.lower().replace("hours", "").strip()

        # Check for a range
        if "-" in time_str:
            low_str, high_str = [part.strip() for part in time_str.split("-", 1)]
            low_hours = float(re.sub(r"\D.", "", low_str))
            high_hours = float(high_str)
            # Calculate average duration in hours
            avg_hours = (low_hours + high_hours) / 2
            return timedelta(hours=avg_hours)
        else:
            # Single value
            hours = float(time_str)
            return timedelta(hours=hours)
    except (ValueError, IndexError) as e:
        print(f"Warning: Could not parse duration string '{time_str}': {e}")
        return None


# --- Main Scraping Function ---
@retry_on_failure(max_retries=2, exceptions=(requests.RequestException,))
@handle_network_errors
def scrape_walk_data_from_file(
    base_url: str,
    headers: dict,
    session: requests.Session,
) -> Walk | None:
    """
    Extracts walk data (name, summary, stats) from a local HTML file.
    """

    try:
        # Send HTTP GET request

        response = session.get(base_url, headers=headers, timeout=15)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        print("Successfully fetched the page.")

        # Parse the HTML content
        soup = BeautifulSoup(response.content, "html.parser")

        # --- Extract Data ---
        data = {}

        # 1. Walk Name
        name_tag = soup.select_one("#content h1")
        data["name"] = name_tag.get_text(strip=True) if name_tag else None

        # 2. Canonical URL (if present)
        canonical_link = soup.select_one('link[rel="canonical"]')
        data["url"] = (
            canonical_link["href"]
            if canonical_link and "href" in canonical_link.attrs
            else None
        )

        # 3. Summary
        # Find the H2 with text "Summary" and get the *next* <p> sibling
        summary_h2 = soup.find("h2", string=lambda t: t and "Summary" in t)
        summary_p = summary_h2.find_next_sibling("p") if summary_h2 else None
        data["summary"] = summary_p.get_text(strip=True) if summary_p else None

        # 4. Walk Statistics (Distance, Time, Ascent)
        stats_dl = soup.select_one("#col dl")
        if stats_dl:
            dts = stats_dl.find_all("dt")
            for dt in dts:
                dt_text = dt.get_text(strip=True).lower()
                dd = dt.find_next_sibling("dd")
                if dd:
                    dd_text = dd.get_text(strip=True)

                    if "distance" in dt_text:
                        # Extract km value
                        match = re.search(r"([\d.]+)\s*km", dd_text)
                        if match:
                            try:
                                data["distance_km"] = float(match.group(1))
                            except ValueError:
                                print(
                                    f"Warning: Could not parse distance from '{dd_text}'"
                                )
                        else:
                            print(
                                f"Warning: Could not find 'km' value in distance string: '{dd_text}'"
                            )

                    elif "time" in dt_text:
                        if "-" in dd_text:
                            data["duration_h"] = TimeLength(
                                dd_text.split("-")[1]
                            ).to_hours()
                        else:
                            data["duration_h"] = TimeLength(dd_text).to_hours()

                    elif "ascent" in dt_text:
                        # Extract meters value
                        match = re.search(r"([\d]+)\s*m", dd_text)
                        if match:
                            try:
                                data["ascent_m"] = int(match.group(1))
                            except ValueError:
                                print(
                                    f"Warning: Could not parse ascent from '{dd_text}'"
                                )
                        else:
                            print(
                                f"Warning: Could not find 'm' value in ascent string: '{dd_text}'"
                            )

        # <a href="https://www.google.com/maps/search/58.55180,-4.68820/">Open in Google Maps</a>
        # 5. Location
        location_tag = soup.select_one('a[href^="https://www.google.com/maps/search/"]')
        if location_tag:
            coords = re.findall(r"[-+]?\d*\.\d+|\d+", location_tag["href"])
            if len(coords) == 2:
                try:
                    coords = Coordinate(
                        latitude=float(coords[0]), longitude=float(coords[1])
                    )
                    data["latitude"] = coords.latitude
                    data["longitude"] = coords.longitude
                except Exception as e:
                    logger.warning("Could not convert coordinates: %s", e)
                    print(f"Warning: Could not convert coordinates: {e}")
            else:
                print(
                    f"Warning: Could not find coordinates in location tag: {location_tag['href']}"
                )

        # --- Validate and Create Walk Object ---
        try:
            data["uuid"] = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"{data['latitude']},{data['longitude']}",
                )
            )
            walk_obj = Walk(**data)
            print("Successfully extracted and validated walk data.")
            return walk_obj
        except ValidationError as e:
            print(f"Data validation error: {e}")
            print(f"Raw extracted data: {data}")
            return None

    except Exception as e:
        logger.exception("Unexpected error during walk scraping of %s", base_url)
        print(f"An unexpected error occurred during scraping: {e}")
        return None


def scrape_walkhighlands(session: requests.Session = None) -> list[Walk]:
    """
    Scrapes area links from the Walkhighlands homepage.

    Args:
        headers (dict): Dictionary of HTTP Headers to send with the request.

    Returns:
        list: A list of dictionaries, where each dictionary contains
              the 'name' and absolute 'url' of an extracted link.
              Returns an empty list if an error occurs or no links are found.
    """
    if session is None:
        session = requests.Session()

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36 Edg/116.0.1938.76",
        "system": "Edge 116.0 Win10",
        "browser": "edge",
        "version": "116.0",
        "os": "win10",
    }
    base_url = "https://www.walkhighlands.co.uk/"

    error_collector = ErrorCollector()

    # Scrape area links with error handling
    area_links = scrape_area_links_from_homepage(base_url, headers, session)
    if not area_links:
        logger.error("Failed to scrape any area links from homepage")
        return []

    logger.info(f"Found {len(area_links)} area links")

    # Scrape sub-area links with error collection
    sub_area_links = []
    for area_link in area_links:
        try:
            links = scrape_sub_area_links_from_area(area_link, headers, session)
            if links:
                sub_area_links.extend(links)
            else:
                error_collector.add_error(
                    "scrape_sub_area",
                    Exception("No sub-area links found"),
                    area_link=area_link,
                )
        except Exception as e:
            logger.exception("Error scraping sub-area %s", area_link)
            error_collector.add_error("scrape_sub_area", e, area_link=area_link)

    if not sub_area_links:
        logger.error("Failed to scrape any sub-area links")
        error_collector.log_summary()
        return []

    logger.info(f"Found {len(sub_area_links)} sub-area links")

    # Scrape walk links with error collection
    walk_links = []
    for sub_area_link in sub_area_links:
        try:
            links = scrape_walks_from_sub_area(sub_area_link, headers, session)
            if links:
                walk_links.extend(links)
            else:
                error_collector.add_error(
                    "scrape_walks",
                    Exception("No walk links found"),
                    sub_area_link=sub_area_link,
                )
        except Exception as e:
            error_collector.add_error("scrape_walks", e, sub_area_link=sub_area_link)

    if not walk_links:
        logger.error("Failed to scrape any walk links")
        error_collector.log_summary()
        return []

    logger.info(f"Found {len(walk_links)} walk links")

    # Scrape individual walk data with error collection
    walks: list[Walk] = []
    for walk_link in walk_links:
        try:
            walk = scrape_walk_data_from_file(walk_link, headers, session)
            if walk:
                walks.append(walk)
            else:
                error_collector.add_error(
                    "scrape_walk_data",
                    Exception("Failed to extract walk data"),
                    walk_link=walk_link,
                )
        except Exception as e:
            error_collector.add_error("scrape_walk_data", e, walk_link=walk_link)

    # Log summary of any errors encountered
    error_collector.log_summary()

    if walks:
        logger.info(
            f"Successfully scraped {len(walks)} walks out of {len(walk_links)} attempted"
        )
    else:
        logger.error("Failed to scrape any valid walk data")

    return walks


# --- Main Execution ---
if __name__ == "__main__":
    # Create cached session
    session = requests_cache.CachedSession(
        cache_name="walkhighlands_cache",
        backend="sqlite",
    )

    # Use the main URL as the base URL for resolving relative links
    walks = scrape_walkhighlands(session)

    if walks:
        db = DataBase()
        for walk in walks:
            db.add("walks", walk)
        db.save("walks.db")
        logger.info(f"Successfully scraped and saved {len(walks)} walks to walks.db")
    else:
        logger.error("No walks were successfully extracted")
