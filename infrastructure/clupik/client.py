from __future__ import annotations

import hashlib
import logging
import random
import re
import time
import urllib.parse
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://clupik.pro"

# Headers "de navegador" completos para reducir la chance de bloqueo por bots.
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
    "Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


@dataclass
class ClupikClient:
    base_url: str = BASE_URL
    min_delay_seconds: float = 0.8
    max_delay_seconds: float = 1.6
    timeout_seconds: int = 20
    max_retries: int = 3


    def __post_init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update(DEFAULT_HEADERS)
        self._last_request_ts: float | None = None

    def _respect_rate_limit(self) -> None:
        if self._last_request_ts is None:
            return
        elapsed = time.monotonic() - self._last_request_ts
        wait_for = random.uniform(self.min_delay_seconds, self.max_delay_seconds)
        remaining = wait_for - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def _handle_pow_challenge(self, response: requests.Response, url: str) -> bool:
        """
        Detecta y resuelve el challenge Proof-of-Work (PoW) que Clupik devuelve
        (típicamente con HTTP 429 y título 'Comprobando tu navegador').
        Devuelve True si resolvió el reto exitosamente.
        """
        text = response.text
        if "Comprobando tu navegador" not in text and "RETO" not in text:
            return False

        reto_m = re.search(r"RETO\s*=\s*'([^']+)'", text)
        firma_m = re.search(r"FIRMA\s*=\s*'([^']+)'", text)
        semilla_m = re.search(r"SEMILLA\s*=\s*'([^']+)'", text)
        bits_m = re.search(r"BITS\s*=\s*(\d+)", text)

        if not (reto_m and firma_m and semilla_m and bits_m):
            return False

        reto = reto_m.group(1)
        firma = firma_m.group(1)
        semilla = semilla_m.group(1)
        bits = int(bits_m.group(1))

        logger.info("Resolviendo reto anti-bot PoW de Clupik (bits=%s)...", bits)
        nonce = self._solve_pow(semilla, bits)
        logger.info("Reto PoW resuelto (nonce=%s). Enviando verificación...", nonce)

        sep = "&" if "?" in url else "?"
        params = urllib.parse.urlencode({
            "_pow_r": reto,
            "_pow_f": firma,
            "_pow_n": str(nonce),
        })
        verify_url = f"{url}{sep}{params}"
        verify_res = self._session.get(verify_url, timeout=self.timeout_seconds)
        self._last_request_ts = time.monotonic()
        if verify_res.status_code in (200, 204):
            logger.info("Verificación anti-bot aceptada.")
            return True
        else:
            logger.warning("Verificación anti-bot falló con código %s", verify_res.status_code)
            return False

    @staticmethod
    def _solve_pow(semilla: str, bits: int) -> int:
        nonce = 0
        while True:
            data = f"{semilla}{nonce}".encode("utf-8")
            h = hashlib.sha256(data).digest()
            val = int.from_bytes(h[:4], "big")
            if (val >> (32 - bits)) == 0:
                return nonce
            nonce += 1

    def _request(self, url: str, allow_404: bool = False) -> requests.Response | None:
        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            self._respect_rate_limit()
            try:
                response = self._session.get(url, timeout=self.timeout_seconds)
                self._last_request_ts = time.monotonic()

                # Si es un reto PoW (aunque venga con código 429)
                if response.status_code == 429 or "Comprobando tu navegador" in response.text:
                    if self._handle_pow_challenge(response, url):
                        # Reintenta el pedido ya verificado
                        self._respect_rate_limit()
                        response = self._session.get(url, timeout=self.timeout_seconds)
                        self._last_request_ts = time.monotonic()

                if response.status_code == 404:
                    if allow_404:
                        return None
                    response.raise_for_status()

                if response.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(
                        "429 en %s, esperando %ss (intento %s/%s)",
                        url, backoff, attempt, self.max_retries,
                    )
                    time.sleep(backoff)
                    continue

                response.raise_for_status()
                return response

            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 404:
                    if allow_404:
                        return None
                    raise
                last_exc = exc
                logger.warning(
                    "Error HTTP al pedir %s (intento %s/%s): %s",
                    url, attempt, self.max_retries, exc,
                )
                time.sleep(2 ** attempt)

            except requests.RequestException as exc:
                last_exc = exc
                logger.warning(
                    "Error al pedir %s (intento %s/%s): %s",
                    url, attempt, self.max_retries, exc,
                )
                time.sleep(2 ** attempt)

        raise RuntimeError(f"No se pudo descargar {url}") from last_exc

    def get(self, path: str, allow_404: bool = False) -> str | None:
        """
        Descarga una URL relativa a BASE_URL y devuelve el HTML como texto.
        Reintenta con backoff exponencial ante errores 429/5xx y resuelve PoW.
        """
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        response = self._request(url, allow_404=allow_404)
        return response.text if response is not None else None

    def get_tournament_list(self, manager_id: int) -> str:
        html = self.get(f"/es/manager/{manager_id}/tournaments")
        if html is None:
            raise RuntimeError(f"Torneos del manager {manager_id} no encontrados (404)")
        return html

    def get_ranking(self, tournament_id: int, phase_id: int | None = None) -> str:
        """
        Sin phase_id devuelve la fase por defecto (la página hace un
        redirect interno a la primera fase, ej FASE REGULAR).
        Con phase_id se pide una fase puntual: COPA DE ORO, PLATA, etc.
        """
        path = f"/es/tournament/{tournament_id}/ranking"
        if phase_id is not None:
            path += f"/{phase_id}"
        html = self.get(path)
        if html is None:
            raise RuntimeError(f"Ranking de torneo {tournament_id} no encontrado (404)")
        return html

    def get_calendar(self, tournament_id: int, phase_id: int) -> str | None:
        html = self.get(f"/es/tournament/{tournament_id}/calendar/{phase_id}/all", allow_404=True)
        if html is None:
            html = self.get(f"/es/tournament/{tournament_id}/calendar/{phase_id}", allow_404=True)
        return html

    def get_ranking_export_xls(self, tournament_id: int, phase_id: int) -> bytes | None:
        """
        El export XLS es binario; usamos `_request()` que maneja rate limit y PoW.
        """
        url = f"{self.base_url}/es/tournament/{tournament_id}/ranking/{phase_id}/export-xls"
        response = self._request(url, allow_404=True)
        return response.content if response is not None else None
