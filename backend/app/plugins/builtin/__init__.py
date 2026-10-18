"""Mitgelieferte Plugins."""

from app.plugins.builtin.habitica import HabiticaPlugin
from app.plugins.builtin.cookidoo import CookidooPlugin
from app.plugins.builtin.homeassistant import HomeAssistantPlugin
from app.plugins.builtin.nextcloud import NextcloudPlugin
from app.plugins.builtin.ntfy import NtfyPlugin
from app.plugins.builtin.paperless import PaperlessPlugin
from app.plugins.builtin.seerr import SeerrPlugin
from app.plugins.builtin.shelfarr import ShelfarrPlugin
from app.plugins.builtin.weather import WeatherPlugin

BUILTIN_PLUGINS = [NextcloudPlugin(), HomeAssistantPlugin(), ShelfarrPlugin(), WeatherPlugin(), CookidooPlugin(), HabiticaPlugin(), PaperlessPlugin(), SeerrPlugin(), NtfyPlugin()]
