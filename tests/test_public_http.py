import importlib.util
import json
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch


HAS_HTTP = importlib.util.find_spec("aiohttp") is not None
if HAS_HTTP:
    import public_http
    from public_http import PublicHTTPError, PublicResolver, checked_url, open_public, public_address, read_limited


def response(status=200, headers=None, body=b"ok", length=None):
    async def chunks(size):
        for start in range(0, len(body), size):
            yield body[start:start + size]
    value = SimpleNamespace(status=status, headers=headers or {}, content_length=length, content=SimpleNamespace(iter_chunked=chunks))
    return Mock(__aenter__=AsyncMock(return_value=value), __aexit__=AsyncMock(return_value=False))


@unittest.skipUnless(HAS_HTTP, "Cài aiohttp để kiểm thử HTTP công khai")
class PublicHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_ip_classification_including_ipv6_and_mapped_addresses(self):
        for address in ("1.1.1.1", "8.8.8.8", "2606:4700:4700::1111", "::ffff:1.1.1.1"):
            self.assertTrue(public_address(address), address)
        for address in ("127.0.0.1", "10.0.0.1", "172.16.0.1", "192.168.1.1", "169.254.169.254", "0.0.0.0", "224.0.0.1", "100.64.0.1", "192.0.2.1", "::1", "fc00::1", "fe80::1", "ff02::1", "::ffff:127.0.0.1", "64:ff9b::7f00:1", "2002:7f00:1::", "example.com"):
            self.assertFalse(public_address(address), address)

    async def test_url_validation_rejects_internal_urls_credentials_and_other_protocols(self):
        for url in ("file:///etc/passwd", "ftp://example.com/file", "http://localhost/a", "http://sub.localhost/a", "http://host.local/a", "http://127.0.0.1/a", "http://10.0.0.1/a", "http://[::1]/a", "http://[::ffff:127.0.0.1]/a", "https://user:password@example.com/a", "https://example.com:99999/a", "https://example.com/a\n", "https://example.com/a b", "http:///missing", "https://[fe80::1%25eth0]/a"):
            with self.subTest(url=url), self.assertRaises(PublicHTTPError) as error:
                checked_url(url)
            self.assertEqual(str(error.exception), "unsafe_url")
        self.assertEqual(str(checked_url("https://example.com/file?q=ok#part")), "https://example.com/file?q=ok")
        self.assertEqual(checked_url("https://[2606:4700:4700::1111]/file").scheme, "https")

    async def test_https_only_rejects_plain_http(self):
        with self.assertRaises(PublicHTTPError):
            checked_url("http://example.com", https_only=True)

    async def test_noncanonical_numeric_hosts_cannot_bypass_the_dns_filter(self):
        for host in ("127.1", "2130706433", "0177.0.0.1", "0", "127.0.0.1."):
            with self.subTest(host=host), self.assertRaises(PublicHTTPError):
                checked_url(f"http://{host}/file")

    async def test_resolver_filters_actual_connection_addresses_without_resolving_twice(self):
        delegate = SimpleNamespace(resolve=AsyncMock(return_value=[{"host": "1.1.1.1"}]), close=AsyncMock())
        with patch.object(public_http.aiohttp.resolver, "DefaultResolver", return_value=delegate):
            resolver = PublicResolver()
        self.assertEqual(await resolver.resolve("example.com", 443), [{"host": "1.1.1.1"}])
        delegate.resolve.assert_awaited_once()
        await resolver.close()
        delegate.close.assert_awaited_once()

    async def test_resolver_rejects_mixed_public_private_or_empty_dns_answers(self):
        for records in ([], [{"host": "127.0.0.1"}], [{"host": "1.1.1.1"}, {"host": "10.0.0.1"}]):
            delegate = SimpleNamespace(resolve=AsyncMock(return_value=records), close=AsyncMock())
            with patch.object(public_http.aiohttp.resolver, "DefaultResolver", return_value=delegate):
                resolver = PublicResolver()
            with self.assertRaises(PublicHTTPError):
                await resolver.resolve("example.com", 443)
            await resolver.close()

    async def test_session_never_uses_environment_proxies_and_closes_its_connector(self):
        async with public_http.public_session() as session:
            self.assertFalse(session.trust_env)
            self.assertFalse(session.auto_decompress)
            self.assertEqual(session.headers["Accept-Encoding"], "identity")
            connector = session.connector
            self.assertIsInstance(connector._resolver, PublicResolver)
        self.assertTrue(connector.closed)

    async def test_relative_redirect_is_followed_manually(self):
        session = SimpleNamespace(get=Mock(side_effect=[response(302, {"Location": "/new"}), response(body=b"result")]))
        async with open_public(session, "https://example.com/old") as result:
            self.assertEqual(await read_limited(result, 20), b"result")
        self.assertEqual(str(session.get.call_args.args[0]), "https://example.com/new")
        self.assertTrue(all(not call.kwargs["allow_redirects"] for call in session.get.call_args_list))

    async def test_redirects_to_private_network_or_tls_downgrade_are_blocked(self):
        for location in ("http://127.0.0.1/a", "https://10.0.0.1/a", "https://localhost/a", "http://example.net/a", "file:///etc/passwd", "https://user:secret@example.net/a"):
            session = SimpleNamespace(get=Mock(return_value=response(302, {"Location": location})))
            with self.subTest(location=location), self.assertRaises(PublicHTTPError):
                async with open_public(session, "https://example.com/old"):
                    self.fail("Unsafe redirect must not be opened")
            session.get.assert_called_once()

    async def test_redirect_loop_is_bounded(self):
        session = SimpleNamespace(get=Mock(side_effect=lambda *args, **kwargs: response(302, {"Location": "/again"})))
        with self.assertRaises(PublicHTTPError) as error:
            async with open_public(session, "https://example.com/old"):
                self.fail("Redirect loop must fail")
        self.assertEqual(error.exception.reason, "redirect")
        self.assertEqual(session.get.call_count, 6)

    async def test_http_error_does_not_store_url_or_response_body(self):
        session = SimpleNamespace(get=Mock(return_value=response(404, body=b"private-token")))
        with self.assertRaises(PublicHTTPError) as error:
            async with open_public(session, "https://example.com/private-token"):
                self.fail("404 must fail")
        self.assertEqual(error.exception.status, 404)
        self.assertNotIn("private-token", str(error.exception))

    async def test_read_limit_covers_declared_and_chunked_bodies(self):
        for length in (1000, None):
            async with response(body=b"x" * 20, length=length) as result:
                with self.assertRaises(PublicHTTPError):
                    await read_limited(result, 10)

    async def test_json_response_must_be_a_small_object(self):
        for value, valid in (({"ok": True}, True), ([], False), ("text", False)):
            session = SimpleNamespace(get=Mock(return_value=response(body=json.dumps(value).encode())))
            @asynccontextmanager
            async def session_factory():
                yield session
            with patch.object(public_http, "public_session", session_factory):
                if valid:
                    self.assertEqual(await public_http.fetch_json("https://example.com/api"), value)
                else:
                    with self.assertRaises(PublicHTTPError):
                        await public_http.fetch_json("https://example.com/api")


if __name__ == "__main__":
    unittest.main()
