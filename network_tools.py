"""Tra IP và đăng ký tên miền; viết lại từ ý tưởng lệnh của source sth cũ."""

import asyncio
import ipaddress
import re

import aiohttp

from i18n import get_text
from public_http import PublicHTTPError, fetch_json, public_address
from shell_commands import clipped_html


def parse_ip(argument):
    try:
        if "%" in argument:
            raise ValueError
        value = ipaddress.ip_address(argument.strip())
        if not public_address(value):
            raise ValueError
        return str(value)
    except ValueError:
        raise ValueError("A public IPv4 or IPv6 address is required") from None


def parse_domain(argument):
    try:
        domain = argument.strip().rstrip(".").encode("idna").decode("ascii").lower()
        labels = domain.split(".")
        if len(domain) > 253 or len(labels) < 2:
            raise ValueError
        if any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels):
            raise ValueError
        if not re.search(r"[a-z]", labels[-1]) or domain.endswith((".local", ".localhost", ".internal")):
            raise ValueError
        return domain
    except (ValueError, UnicodeError):
        raise ValueError("A domain name without a URL, path or port is required") from None


def field(value, limit=180):
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        return "—"
    return clipped_html(" ".join(str(value).split()) or "—", limit)[0]


def format_ip(data, target, lang):
    if data.get("success") is not True:
        raise PublicHTTPError("not_found")
    connection = data.get("connection")
    connection = connection if isinstance(connection, dict) else {}
    return get_text(
        "lookup_ip_result", lang, ip=field(target), country=field(data.get("country")),
        region=field(data.get("region")), city=field(data.get("city")),
        isp=field(connection.get("isp")), org=field(connection.get("org")), asn=field(connection.get("asn")),
    )


def format_domain(data, target, lang):
    if data.get("objectClassName") != "domain":
        raise PublicHTTPError("not_found")
    dates = {}
    events = data.get("events", [])
    for event in events[:30] if isinstance(events, list) else []:
        if isinstance(event, dict) and isinstance(event.get("eventAction"), str):
            dates[event["eventAction"]] = event.get("eventDate")
    registrar = None
    entities = data.get("entities", [])
    for entity in entities[:30] if isinstance(entities, list) else []:
        if not isinstance(entity, dict) or not isinstance(entity.get("roles"), list) or "registrar" not in entity["roles"]:
            continue
        card = entity.get("vcardArray")
        if isinstance(card, list) and len(card) == 2 and isinstance(card[1], list):
            registrar = next((item[3] for item in card[1][:30] if isinstance(item, list) and len(item) == 4 and item[0] == "fn"), None)
        if registrar:
            break
    nameservers = data.get("nameservers", [])
    ns = [field(item.get("ldhName"), 100) for item in nameservers[:8] if isinstance(item, dict)] if isinstance(nameservers, list) else []
    status = data.get("status", [])
    statuses = [field(item, 100) for item in status[:6]] if isinstance(status, list) else []
    return get_text(
        "lookup_whois_result", lang, domain=field(target), registrar=field(registrar),
        registered=field(dates.get("registration")), expires=field(dates.get("expiration")),
        changed=field(dates.get("last changed")), status=", ".join(statuses) or "—", ns=", ".join(ns) or "—",
    )


async def lookup_message(command, argument, edit, lang="vi"):
    try:
        target = parse_ip(argument) if command == "ip" else parse_domain(argument)
    except ValueError:
        await edit(get_text(f"lookup_{command}_usage", lang), parse_mode="html")
        return
    await edit(get_text("lookup_working", lang), parse_mode="html")
    try:
        url = f"https://ipwho.is/{target}" if command == "ip" else f"https://rdap.org/domain/{target}"
        # Giới hạn cả chuỗi redirect, không phải chỉ từng HTTP request.
        data = await asyncio.wait_for(fetch_json(url), timeout=15)
        text = format_ip(data, target, lang) if command == "ip" else format_domain(data, target, lang)
    except (aiohttp.ClientError, asyncio.TimeoutError, PublicHTTPError, ValueError) as exc:
        key = "lookup_failed"
        if isinstance(exc, PublicHTTPError):
            if exc.status == 429:
                key = "lookup_rate_limited"
            elif exc.status == 404 or exc.reason == "not_found":
                key = "lookup_missing"
        text = get_text(key, lang)
    await edit(text, parse_mode="html")
