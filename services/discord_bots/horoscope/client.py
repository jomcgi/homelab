from typing import Literal, NamedTuple
import discord
from enum import Enum
from services.discord_bots.shared.discord_client import DiscordBot
import requests
from bs4 import BeautifulSoup
import re


class StarSign(Enum):
    ARIES = 1
    TAURUS = 2
    GEMINI = 3
    CANCER = 4
    LEO = 5
    VIRGO = 6
    LIBRA = 7
    SCORPIO = 8
    SAGITTARIUS = 9
    CAPRICORN = 10
    AQUARIUS = 11
    PISCES = 12


class Horoscope(NamedTuple):
    type: str
    cadence: Literal["daily-today", "weekly"]


class HoroscopeTypes(Enum):
    general = Horoscope("general", "daily-today")
    love = Horoscope("love", "daily-today")
    career = Horoscope("career", "daily-today")
    money = Horoscope("money", "weekly")
    wellness = Horoscope("wellness", "daily-today")


class HoroscopeBot(DiscordBot):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def on_message(self, message: discord.Message) -> None:
        """"""
        if message.author.id == self.user.id or message.author.bot:
            return
        if message.channel.name not in ["bot-test", "general"]:
            return
        if message.content.startswith("!gemini"):
            return
        star_sign = _extract_star_sign(message.content)
        if star_sign is None:
            return

        horoscope = _get_horoscope_messages(star_sign)
        for horoscope_message in horoscope:
            await message.channel.send(horoscope_message)


def _extract_star_sign(message: str) -> StarSign | None:
    for star_sign in StarSign:
        if star_sign.name.lower() in message.lower():
            return star_sign
    return None


def _fetch_horoscope(star_sign: StarSign, horoscope: Horoscope) -> str:
    url = f"https://www.horoscope.com/us/horoscopes/{horoscope.type}/horoscope-{horoscope.type}-{horoscope.cadence}.aspx?sign={star_sign.value}"
    res = requests.get(url)
    soup = BeautifulSoup(res.content, "html.parser")
    data = soup.find("div", attrs={"class": "main-horoscope"})
    return data.p.text


def _remove_dates_from_horoscope(horoscope: str) -> str:
    pattern = r" - (?!(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b)(.+)$"
    match = re.search(pattern, horoscope)
    return match.group(1)


def _get_horoscope_messages(star_sign: StarSign) -> list[str]:
    horoscope_messages = []
    current_message = f"# {star_sign.name.capitalize()} Horoscope\n"
    for h in HoroscopeTypes:
        horoscope_type = h.value
        horoscope = _fetch_horoscope(star_sign, horoscope_type)
        horoscope_message = f"\n### {horoscope_type.type.capitalize()}:\n> {_remove_dates_from_horoscope(horoscope)}"
        if len(current_message + horoscope_message) < 2000:
            current_message += horoscope_message
        else:
            horoscope_messages.append(current_message)
            current_message = horoscope_message
    horoscope_messages.append(current_message)
    return horoscope_messages
