"""Config flow integrace mojeodpadky.cz."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import (
    InvalidAuth,
    MojeOdpadkyClient,
    MojeOdpadkyError,
    Schedule,
    SlugNotFound,
)
from .const import (
    CONF_SCAN_INTERVAL,
    CONF_SCHEDULES,
    CONF_SLUG,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DOMAIN,
    SCAN_INTERVAL_CHOICES,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


def _hodiny(pocet: int) -> str:
    """Jednotně číslem, jen se správným pádem: 1 hodina, 3 hodiny, 6 hodin."""
    if pocet == 1:
        return "1 hodina"
    if pocet < 5:
        return f"{pocet} hodiny"
    return f"{pocet} hodin"


def _interval_selector() -> SelectSelector:
    """Výběr, jak často se data stahují."""
    return SelectSelector(
        SelectSelectorConfig(
            options=[
                SelectOptionDict(value=str(hours), label=_hodiny(hours))
                for hours in SCAN_INTERVAL_CHOICES
            ],
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


def _schedule_options(schedules: list[Schedule]) -> list[SelectOptionDict]:
    return [
        SelectOptionDict(value=str(item.schedule_id), label=item.label)
        for item in schedules
    ]


class MojeOdpadkyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Přihlášení a výběr harmonogramů."""

    VERSION = 1
    # Úpravy starších instalací viz async_migrate_entry v __init__.py.
    MINOR_VERSION = 3

    def __init__(self) -> None:
        self._client: MojeOdpadkyClient | None = None
        self._schedules: list[Schedule] = []
        self._data: dict[str, Any] = {}
        self._town: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Krok 1 - přihlašovací údaje."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Obec si integrace zjistí sama z přihlášeného webu,
            # uživatel ji nezadává.
            client = MojeOdpadkyClient(
                login=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
            )
            try:
                body = await client.async_fetch_page()
            except InvalidAuth:
                _LOGGER.warning(
                    "Přihlášení účtu %s: server odmítl jméno nebo heslo",
                    user_input[CONF_USERNAME],
                )
                errors["base"] = "invalid_auth"
            except SlugNotFound as err:
                _LOGGER.warning(
                    "Přihlášení účtu %s prošlo, ale obec se nezjistila: %s",
                    user_input[CONF_USERNAME],
                    err,
                )
                errors["base"] = "slug_not_found"
            except MojeOdpadkyError as err:
                # Pod "nepodařilo se spojit" se schovává víc různých příčin;
                # bez skutečné zprávy v logu se nedá poznat, která to je.
                _LOGGER.warning(
                    "Přihlášení účtu %s selhalo (obec: %s): %s",
                    user_input[CONF_USERNAME],
                    client.slug or "nezjištěna",
                    err,
                )
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(
                    f"{user_input[CONF_USERNAME].lower()}@{client.slug}"
                )
                self._abort_if_unique_id_configured()

                self._client = client
                self._schedules = client.parse_schedules(body)
                self._town = await client.async_fetch_town()
                self._data = {
                    CONF_USERNAME: user_input[CONF_USERNAME],
                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                    CONF_SLUG: client.slug,
                }
                return await self.async_step_schedules()

            await client.async_close()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    def _entry_title(self) -> str:
        """Název služby a tím i zařízení a začátku všech entity_id.

        Jeden účet v obci se jmenuje prostě podle obce. Další účet ve stejné
        obci (třeba člen rodiny) dostane do závorky login - jinak by měly
        dvě zařízení stejný název a entity by se lišily jen koncovkou _2.
        """
        obec = self._town or self._data[CONF_SLUG]
        stejna_obec = [
            entry
            for entry in self._async_current_entries()
            if entry.data.get(CONF_SLUG) == self._data[CONF_SLUG]
        ]
        if stejna_obec:
            return f"{obec} ({self._data[CONF_USERNAME]})"
        return obec

    async def async_step_schedules(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Krok 2 - výběr harmonogramů."""
        if user_input is not None:
            if self._client is not None:
                await self._client.async_close()
            return self.async_create_entry(
                title=self._entry_title(),
                data=self._data,
                options={
                    CONF_SCHEDULES: user_input[CONF_SCHEDULES],
                    CONF_SCAN_INTERVAL: int(
                        user_input.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_HOURS
                        )
                    ),
                },
            )

        preselected = [
            str(item.schedule_id) for item in self._schedules if item.subscribed
        ]

        schema = vol.Schema(
            {
                vol.Required(CONF_SCHEDULES, default=preselected): SelectSelector(
                    SelectSelectorConfig(
                        options=_schedule_options(self._schedules),
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=str(DEFAULT_SCAN_INTERVAL_HOURS)
                ): _interval_selector(),
            }
        )
        return self.async_show_form(
            step_id="schedules",
            data_schema=schema,
            description_placeholders={
                "obec": self._town or self._data.get(CONF_SLUG, "")
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Vrátit options flow."""
        return MojeOdpadkyOptionsFlow(config_entry)


class MojeOdpadkyOptionsFlow(OptionsFlow):
    """Pozdější změna výběru harmonogramů."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Zobrazit výběr harmonogramů."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    **user_input,
                    CONF_SCAN_INTERVAL: int(
                        user_input.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_HOURS
                        )
                    ),
                }
            )

        coordinator = self._entry.runtime_data
        schedules = coordinator.data.schedules if coordinator.data else []

        current = self._entry.options.get(
            CONF_SCHEDULES,
            [str(item.schedule_id) for item in schedules if item.subscribed],
        )

        schema = vol.Schema(
            {
                vol.Required(CONF_SCHEDULES, default=list(current)): SelectSelector(
                    SelectSelectorConfig(
                        options=_schedule_options(schedules),
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=str(
                        self._entry.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_HOURS
                        )
                    ),
                ): _interval_selector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
