"""Minimal Vinted catalog client using the public web API.

Auth flow: a GET to the homepage sets an ``access_token_web`` cookie; the
catalog API accepts it as a Bearer token when the request carries ordinary
browser headers. Tokens expire, so the client re-bootstraps on 401/403.
"""

from __future__ import annotations

import time

import requests

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

CATALOG_MEN = 5


class VintedClient:
    def __init__(self, domain: str = "vinted.fr", delay_s: float = 1.0):
        self.base = f"https://www.{domain}"
        self.delay_s = delay_s
        self._last_request = 0.0
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": UA,
                "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
                "Sec-Ch-Ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Linux"',
            }
        )
        self._bootstrap()

    def _bootstrap(self) -> None:
        r = self.session.get(self.base + "/", timeout=30)
        r.raise_for_status()
        token = self.session.cookies.get("access_token_web")
        if not token:
            raise RuntimeError("no access_token_web cookie — bot wall or layout change")
        self._api_headers = {
            "Accept": "application/json, text/plain, */*",
            "Authorization": f"Bearer {token}",
            "Referer": self.base + "/catalog",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }

    def _throttle(self) -> None:
        wait = self.delay_s - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def search(
        self,
        text: str,
        *,
        catalog_id: int | None = CATALOG_MEN,
        per_page: int = 48,
        page: int = 1,
        order: str = "relevance",
        price_to: float | None = None,
        currency: str = "EUR",
    ) -> list[dict]:
        """One page of catalog results as raw item dicts."""
        params: dict = {
            "search_text": text,
            "per_page": per_page,
            "page": page,
            "order": order,
        }
        if catalog_id:
            params["catalog_ids"] = str(catalog_id)
        if price_to:
            params["price_to"] = price_to
            params["currency"] = currency

        self._throttle()
        r = self.session.get(
            self.base + "/api/v2/catalog/items",
            params=params,
            headers=self._api_headers,
            timeout=30,
        )
        if r.status_code in (401, 403):
            self._bootstrap()
            self._throttle()
            r = self.session.get(
                self.base + "/api/v2/catalog/items",
                params=params,
                headers=self._api_headers,
                timeout=30,
            )
        r.raise_for_status()
        return r.json().get("items", [])
