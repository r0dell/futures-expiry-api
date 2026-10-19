"""Futures Expiry API mit x402-Bezahlung (USDC auf Base).

Umgebungsvariablen:
  PAY_TO              Deine Wallet-Adresse (0x...), hierhin gehen die Zahlungen. Pflicht.
  X402_NETWORK        "testnet" (Base Sepolia, Standard) oder "mainnet" (Base).
  CDP_API_KEY_ID      Coinbase-Developer-Platform-Key. Für mainnet und Bazaar-Listing nötig.
  CDP_API_KEY_SECRET  dazugehöriges Secret.
  PUBLIC_URL          Öffentliche https-Adresse des Dienstes (für die Bazaar-Beschreibung).

Start:  uvicorn paid_app:app --host 0.0.0.0 --port 8000
Gratis:  /v1/products, /health, /docs
Bezahlt: /v1/front-month, /v1/expirations, /v1/roll-calendar
"""
import os
import re

from x402 import x402ResourceServer
from x402.extensions.bazaar import (
    OutputConfig,
    bazaar_resource_server_extension,
    declare_discovery_extension,
)
from x402.http import FacilitatorConfig, HTTPFacilitatorClient
from x402.http.middleware.fastapi import PaymentMiddlewareASGI
from x402.http.types import PaymentOption, RouteConfig
from x402.mechanisms.evm.exact import ExactEvmServerScheme

from app import app

NETWORKS = {"testnet": "eip155:84532", "mainnet": "eip155:8453"}
TESTNET_FACILITATOR = os.environ.get("FACILITATOR_URL", "https://x402.org/facilitator")

PAY_TO = os.environ.get("PAY_TO", "").strip()
if not re.fullmatch(r"0x[0-9a-fA-F]{40}", PAY_TO):
    raise SystemExit("PAY_TO fehlt oder ist keine gültige Wallet-Adresse (0x + 40 Hex-Zeichen).")

MODE = os.environ.get("X402_NETWORK", "testnet").lower()
if MODE not in NETWORKS:
    raise SystemExit("X402_NETWORK muss 'testnet' oder 'mainnet' sein.")
NETWORK = NETWORKS[MODE]

CDP_ID = os.environ.get("CDP_API_KEY_ID", "").strip().strip('"\'').strip()
CDP_SECRET = os.environ.get("CDP_API_KEY_SECRET", "").strip().strip('"\'').strip()
if "BEGIN" in CDP_SECRET:
    CDP_SECRET = CDP_SECRET.replace("\\n", "\n")  # PEM aus einzeiligem Feld


def _describe_cdp_keys() -> str:
    """Format der Keys beschreiben, ohne Werte preiszugeben."""
    id_kind = ("uuid" if re.fullmatch(r"[0-9a-fA-F-]{36}", CDP_ID)
               else "organizations-path" if CDP_ID.startswith("organizations/") else "other")
    if "BEGIN EC PRIVATE KEY" in CDP_SECRET:
        sec_kind = "ec-pem"
    else:
        try:
            import base64
            sec_kind = f"base64-{len(base64.b64decode(CDP_SECRET, validate=True))}bytes"
        except Exception:
            sec_kind = "unparseable"
    return f"CDP key: id={id_kind} (len {len(CDP_ID)}), secret={sec_kind} (len {len(CDP_SECRET)})"


if CDP_ID and CDP_SECRET:
    from cdp.x402 import create_facilitator_config
    print(_describe_cdp_keys(), flush=True)
    facilitator_cfg = create_facilitator_config(CDP_ID, CDP_SECRET)
elif MODE == "mainnet":
    raise SystemExit("Für mainnet werden CDP_API_KEY_ID und CDP_API_KEY_SECRET benötigt.")
else:
    facilitator_cfg = FacilitatorConfig(url=TESTNET_FACILITATOR)

server = x402ResourceServer(HTTPFacilitatorClient(facilitator_cfg))
server.register(NETWORK, ExactEvmServerScheme())
server.register_extension(bazaar_resource_server_extension)

PRODUCT_SCHEMA = {
    "type": "string",
    "description": "Futures product: ES, MES, NQ, MNQ, YM, MYM, RTY, M2K, FDAX, FDXM, FESX, FSMI",
}
AT_SCHEMA = {"type": "string",
             "description": "Optional ISO 8601 time with offset, e.g. 2026-12-11T15:00:00Z. Default: now."}
SVC = "Futures Expiry API"


def pay(price: str) -> PaymentOption:
    return PaymentOption(scheme="exact", pay_to=PAY_TO, price=price, network=NETWORK)


routes = {
    "GET /v1/front-month": RouteConfig(
        accepts=pay("$0.01"),
        description="Returns the current front-month contract of a CME or Eurex index future, the most "
                    "active contract after the roll date, days to expiration and the exact last trading time.",
        mime_type="application/json", service_name=SVC,
        tags=["finance", "futures", "expiration", "rollover", "trading"],
        extensions=declare_discovery_extension(
            input={"product": "ES", "at": "2026-12-11T15:00:00Z"},
            input_schema={"properties": {"product": PRODUCT_SCHEMA, "at": AT_SCHEMA}, "required": ["product"]},
            output=OutputConfig(example={
                "product": "ES", "front_contract": "ESZ6", "most_active_contract": "ESH7",
                "after_roll_date": True, "days_to_expiration": 6.77}),
        ),
    ),
    "GET /v1/expirations": RouteConfig(
        accepts=pay("$0.01"),
        description="Returns the next quarterly contracts of a CME or Eurex index future with contract "
                    "symbol, last trading day, trading end time in UTC and local time, and roll date.",
        mime_type="application/json", service_name=SVC,
        tags=["finance", "futures", "expiration", "calendar"],
        extensions=declare_discovery_extension(
            input={"product": "NQ", "count": "2"},
            input_schema={"properties": {"product": PRODUCT_SCHEMA,
                                         "count": {"type": "string", "description": "Number of contracts, 1-12. Default 4."},
                                         "at": AT_SCHEMA}, "required": ["product"]},
            output=OutputConfig(example={
                "product": "NQ", "contracts": [
                    {"symbol": "NQZ6", "last_trading_day": "2026-12-18", "roll_date": "2026-12-10",
                     "trading_ends": {"utc": "2026-12-18T14:30:00+00:00", "local": "2026-12-18T09:30:00-05:00"}}]}),
        ),
    ),
    "GET /v1/roll-calendar": RouteConfig(
        accepts=pay("$0.02"),
        description="Returns all four quarterly expirations and roll dates of a CME or Eurex index future "
                    "for one calendar year, with holiday adjustments.",
        mime_type="application/json", service_name=SVC,
        tags=["finance", "futures", "rollover", "calendar"],
        extensions=declare_discovery_extension(
            input={"product": "FDAX", "year": "2027"},
            input_schema={"properties": {"product": PRODUCT_SCHEMA,
                                         "year": {"type": "string", "description": "Calendar year, e.g. 2027"}},
                          "required": ["product", "year"]},
            output=OutputConfig(example={
                "product": "FDAX", "year": 2027, "contracts": [
                    {"symbol": "FDAXH7", "last_trading_day": "2027-03-19", "roll_date": "2027-03-11"}]}),
        ),
    ),
}

app.add_middleware(PaymentMiddlewareASGI, routes=routes, server=server)
app.title = f"Futures Expiry API ({MODE})"
