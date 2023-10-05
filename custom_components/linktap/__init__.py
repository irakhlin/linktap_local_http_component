import asyncio
import logging
import random
from datetime import timedelta
from json.decoder import JSONDecodeError

import async_timeout
import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from h11 import Data
from homeassistant import core
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.exceptions import IntegrationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (DataUpdateCoordinator,
                                                      UpdateFailed)

from .const import DOMAIN, GW_ID, GW_IP, NAME, PLATFORMS, TAP_ID
from .linktap_local import LinktapLocal

_LOGGER = logging.getLogger(__name__)

async def async_setup(_hass, _config):
    return True

async def async_setup_entry(hass: core.HomeAssistant, entry: ConfigEntry)-> bool:
    """Set up the platform."""

    gw_ip = entry.data.get(GW_IP)

    linker = LinktapLocal()
    linker.set_ip(gw_ip)
    try:
        gw_id = await linker.get_gw_id()
    except JSONDecodeError:
        try:
            await asyncio.sleep(random.randint(1,3))
            gw_id = await linker.get_gw_id()
        except JSONDecodeError:
            await asyncio.sleep(random.randint(1,3))
            gw_id = await linker.get_gw_id()

    _LOGGER.debug(f"Found GW_ID: {gw_id}")

    gateway_config = await linker.get_gw_config(gw_id)
    if "end_dev" not in gateway_config:
        raise IntegrationError("Linktap Gateway needs to be updated")

    devices = {
        "devs": gateway_config["end_dev"],
        "names": gateway_config["dev_name"],
    }
    _LOGGER.debug(f"{gw_id}: Found devices: {devices}")

    coordinator_conf = {
        GW_IP: gw_ip,
        GW_ID: gw_id,
    }
    counter = 0
    tap_list = []
    for tap_id in devices["devs"]:
        coordinator = LinktapCoordinator(hass, linker, coordinator_conf, tap_id)
        device_name = devices["names"][counter]
        tap_list.append({
            NAME: device_name,
            TAP_ID: tap_id,
            GW_ID: gw_id,
            "coordinator": coordinator
        })
        counter = counter + 1
        await coordinator.async_config_entry_first_refresh()
        _LOGGER.debug(f"Coordinator has synced for {tap_id}")
    _LOGGER.debug(f"{gw_id}: List of Taps: {tap_list}")

    vol_unit = gateway_config["vol_unit"]
    _LOGGER.debug(f"{gw_id}: Setting volume unit to {vol_unit}")

    conf = {
        GW_IP: gw_ip,
        GW_ID: gw_id,
        "taps": tap_list,
        "vol_unit": vol_unit,
    }


    hass.data[DOMAIN] = {
        "conf": conf,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)


    return True

async def async_unload_entry(hass: core.HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a component config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok

class LinktapCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, linker, conf, tap_id):
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=13),
        )
        self.tap_api = linker
        self.conf = conf
        self.hass = hass
        self.tap_id = tap_id

    def get_gw_id(self):
        return self.conf[GW_ID]

    async def _async_update_data(self):
        """Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """

        #tap_id = self.conf["taps"][TAP_ID]
        gw_id = self.get_gw_id()
        _LOGGER.debug(f"GW {gw_id}: Updating data for {self.tap_id}...")

        try:
            # Note: asyncio.TimeoutError and aiohttp.ClientError are already
            # handled by the data update coordinator.
            async with async_timeout.timeout(10):
                return await self.tap_api.fetch_data(gw_id, self.tap_id)
        except:# ApiAuthError as err:
            await asyncio.sleep(random.randint(1,3))
            async with async_timeout.timeout(10):
                return await self.tap_api.fetch_data(gw_id, self.tap_id)
            # Raising ConfigEntryAuthFailed will cancel future updates
            # and start a config flow with SOURCE_REAUTH (async_step_reauth)
        #    raise ConfigEntryAuthFailed from err
        #except ApiError as err:
        #    raise UpdateFailed(f"Error communicating with API: {err}")
