"""HTTP công khai cho tiện ích: kiểm tra URL/DNS/redirect, không truy cập mạng nội bộ."""

import ipaddress
import json
import re
import socket
from contextlib import asynccontextmanager

import aiohttp
from yarl import URL


class PublicHTTPError(Exception):
    def __init__(self, reason, status=0):
        self.reason = reason
        self.status = status
        super().__init__(reason)  # Không giữ URL, query, header hay body trong lỗi.


def public_address(value):
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped:
            return public_address(address.ipv4_mapped)
        # Không cho địa chỉ tunnel/NAT64 đi vòng qua kiểm tra IPv4 nội bộ.
        if address.sixtofour or address.teredo or address in ipaddress.ip_network("64:ff9b:1::/48"):
            return False
        if address in ipaddress.ip_network("64:ff9b::/96"):
            return public_address(ipaddress.IPv4Address(int(address) & 0xffffffff))
    return address.is_global and not (address.is_multicast or address.is_reserved or address.is_unspecified)


def checked_url(value, *, https_only=False):
    try:
        if not isinstance(value, str) or len(value) > 4096 or re.search(r"[\x00-\x20\x7f]", value):
            raise ValueError
        url = URL(value)
        if url.scheme not in (("https",) if https_only else ("http", "https")):
            raise ValueError
        host = url.host
        if not host or url.user is not None or url.password is not None or not url.port or "%" in host:
            raise ValueError
        host = host.rstrip(".").lower()
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            raise ValueError
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        # aiohttp có thể coi dạng rút gọn/số nguyên (127.1, 2130706433) là IP
        # và bỏ qua custom resolver. Chỉ nhận literal IP chuẩn đã kiểm tra.
        if address is None and (":" in host or host.replace(".", "").isdigit()):
            raise ValueError
        if address is not None and not public_address(address):
            raise ValueError
        return url.with_fragment(None)
    except (ValueError, TypeError, UnicodeError):
        raise PublicHTTPError("unsafe_url") from None


class PublicResolver(aiohttp.abc.AbstractResolver):
    """Lọc chính IP đưa cho connector, không resolve hai lần gây DNS rebinding."""

    def __init__(self):
        self.resolver = aiohttp.resolver.DefaultResolver()

    async def resolve(self, host, port=0, family=socket.AF_INET):
        records = await self.resolver.resolve(host, port, family)
        if not records or any(not public_address(record["host"]) for record in records):
            raise PublicHTTPError("unsafe_url")
        return records

    async def close(self):
        await self.resolver.close()


@asynccontextmanager
async def public_session(timeout=15):
    resolver = PublicResolver()
    connector = aiohttp.TCPConnector(resolver=resolver)
    try:
        async with aiohttp.ClientSession(
            connector=connector, trust_env=False, auto_decompress=False,
            timeout=aiohttp.ClientTimeout(total=timeout, sock_read=min(timeout, 30)),
            headers={"User-Agent": "tg-name", "Accept-Encoding": "identity"},
        ) as session:
            yield session
    finally:
        await connector.close()
        await resolver.close()


@asynccontextmanager
async def open_public(session, value, *, https_only=False):
    url = checked_url(value, https_only=https_only)
    for hop in range(6):
        async with session.get(url, allow_redirects=False) as response:
            if response.status in (301, 302, 303, 307, 308):
                location = response.headers.get("Location")
                if hop == 5 or not location:
                    raise PublicHTTPError("redirect")
                try:
                    target = url.join(URL(location))
                except (ValueError, TypeError, UnicodeError):
                    raise PublicHTTPError("unsafe_url") from None
                url = checked_url(str(target), https_only=https_only or url.scheme == "https")
                continue
            if not 200 <= response.status < 300:
                raise PublicHTTPError("http_status", response.status)
            yield response
            return


async def read_limited(response, limit):
    if response.content_length is not None and response.content_length > limit:
        raise PublicHTTPError("too_large")
    data = bytearray()
    async for chunk in response.content.iter_chunked(65536):
        if len(data) + len(chunk) > limit:
            raise PublicHTTPError("too_large")
        data.extend(chunk)
    return bytes(data)


async def fetch_json(url):
    async with public_session() as session:
        async with open_public(session, url, https_only=True) as response:
            try:
                data = json.loads(await read_limited(response, 256 * 1024))
            except (ValueError, UnicodeError):
                raise PublicHTTPError("invalid_response") from None
            if not isinstance(data, dict):
                raise PublicHTTPError("invalid_response")
            return data
