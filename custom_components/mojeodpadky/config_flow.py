"""Config flow integrace mojeodpadky.cz."""

from __future__ import annotations

import logging
from collections.abc import Mapping
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
from homeassistant.helpers.aiohttp_client import async_create_clientsession
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

STEP_REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_PASSWORD): str})


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
    MINOR_VERSION = 4

    def __init__(self) -> None:
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
            # Vlastní session jen pro ověření; odpojí se vždycky, i při
            # zamítnutí "už nastaveno". Druhý krok už ji nepotřebuje.
            session = async_create_clientsession(self.hass, auto_cleanup=False)
            client = MojeOdpadkyClient(
                login=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                session=session,
            )
            try:
                body = await client.async_fetch_page()
                schedules = client.parse_schedules(body)
                town = await client.async_fetch_town()
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
            except Exception:  # noqa: BLE001 - průvodce nesmí spadnout
                _LOGGER.exception(
                    "Neočekávaná chyba při přihlášení účtu %s",
                    user_input[CONF_USERNAME],
                )
                errors["base"] = "unknown"
            finally:
                session.detach()

            if not errors:
                await self.async_set_unique_id(
                    f"{user_input[CONF_USERNAME].lower()}@{client.slug}"
                )
                self._abort_if_unique_id_configured()

                self._schedules = schedules
                self._town = town
                self._data = {
                    CONF_USERNAME: user_input[CONF_USERNAME],
                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                    CONF_SLUG: client.slug,
                }
                return await self.async_step_schedules()

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

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Server odmítl uložené heslo - nejspíš se na webu změnilo."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Zeptat se na nové heslo, ověřit ho a uložit.

        Jméno se nemění - je součástí unique_id a určuje, ke kterému účtu
        entry patří. Obec se při ověření zjistí znovu, jen pro kontrolu.
        """
        entry = self._get_reauth_entry()
        username = entry.data[CONF_USERNAME]
        errors: dict[str, str] = {}

        if user_input is not None:
            session = async_create_clientsession(self.hass, auto_cleanup=False)
            client = MojeOdpadkyClient(
                login=username,
                password=user_input[CONF_PASSWORD],
                slug=entry.data.get(CONF_SLUG),
                session=session,
            )
            try:
                await client.async_fetch_page()
            except InvalidAuth:
                _LOGGER.warning(
                    "Opětovné přihlášení účtu %s: server odmítl heslo", username
                )
                errors["base"] = "invalid_auth"
            except MojeOdpadkyError as err:
                _LOGGER.warning(
                    "Opětovné přihlášení účtu %s selhalo: %s", username, err
                )
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001 - průvodce nesmí spadnout
                _LOGGER.exception(
                    "Neočekávaná chyba při opětovném přihlášení účtu %s", username
                )
                errors["base"] = "unknown"
            finally:
                session.detach()

            if not errors:
                return self.async_update_reload_and_abort(
                    entry,
                    data={**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]},
                    reason="reauth_successful",
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_SCHEMA,
            errors=errors,
            description_placeholders={"username": username},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Vrátit options flow."""
        return MojeOdpadkyOptionsFlow()


class MojeOdpadkyOptionsFlow(OptionsFlow):
    """Pozdější změna výběru harmonogramů."""

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

        # Služba, která se nenačetla (výpadek webu, špatné heslo), seznam
        # harmonogramů nemá. Prázdný výběr by se uložením tiše smazal.
        coordinator = getattr(self.config_entry, "runtime_data", None)
        if coordinator is None or not coordinator.data:
            return self.async_abort(reason="not_loaded")
        schedules = coordinator.data.schedules

        # Zaškrtnuté je to, co je na webu opravdu přihlášené - ne výběr
        # uložený při instalaci. Web sám přihlašuje třeba nový ročník
        # harmonogramu; kdyby tu nebyl zaškrtnutý, uložení formuláře by ho
        # bralo jako odškrtnutí a na webu odhlásilo.
        current = [str(item.schedule_id) for item in schedules if item.subscribed]

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
                        self.config_entry.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_HOURS
                        )
                    ),
                ): _interval_selector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
