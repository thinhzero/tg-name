import asyncio
import importlib.util
import unittest
from unittest.mock import AsyncMock, patch


HAS_HTTP = importlib.util.find_spec("aiohttp") is not None
if HAS_HTTP:
    import network_tools
    from network_tools import format_domain, format_ip, lookup_message, parse_domain, parse_ip
    from public_http import PublicHTTPError


@unittest.skipUnless(HAS_HTTP, "Cài aiohttp để kiểm thử tra cứu")
class NetworkLookupTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_ip_and_domain_normalization(self):
        self.assertEqual(parse_ip(" 1.1.1.1 "), "1.1.1.1")
        self.assertEqual(parse_ip("2606:4700:4700:0000:0000:0000:0000:1111"), "2606:4700:4700::1111")
        self.assertEqual(parse_domain(" EXAMPLE.COM. "), "example.com")
        self.assertEqual(parse_domain("tên.vn"), "xn--tn-eja.vn")

    async def test_bad_targets_do_not_make_http_requests(self):
        targets = {"ip": ("", "localhost", "127.0.0.1", "10.0.0.1", "example.com", "https://1.1.1.1", "2606:4700::1%eth0"), "whois": ("", "localhost", "127.0.0.1", "https://example.com", "example.com/a", "example.com:443", "user@example.com", "-bad.com", "a" * 64 + ".com", "host.local")}
        with patch.object(network_tools, "fetch_json", new=AsyncMock()) as fetch:
            for command, values in targets.items():
                for value in values:
                    edit = AsyncMock()
                    await lookup_message(command, value, edit)
                    edit.assert_awaited_once()
        fetch.assert_not_awaited()

    async def test_ip_lookup_uses_https_and_formats_both_languages(self):
        for lang in ("vi", "en"):
            edit = AsyncMock()
            data = {"success": True, "country": "<country>", "connection": {"isp": "A & B", "asn": 123}}
            with patch.object(network_tools, "fetch_json", new=AsyncMock(return_value=data)) as fetch:
                await lookup_message("ip", "1.1.1.1", edit, lang)
            fetch.assert_awaited_once_with("https://ipwho.is/1.1.1.1")
            self.assertEqual(edit.await_count, 2)
            text = edit.call_args.args[0]
            self.assertIn("&lt;country&gt;", text)
            self.assertIn("A &amp; B", text)
            self.assertNotIn("<country>", text)

    async def test_domain_lookup_uses_rdap_not_html_scraping(self):
        data = {
            "objectClassName": "domain", "status": ["active"],
            "events": [{"eventAction": "registration", "eventDate": "2020-01-01T00:00:00Z"}],
            "entities": [{"roles": ["registrar"], "vcardArray": ["vcard", [["fn", {}, "text", "Registrar <Inc>"]]]}, {"roles": ["registrant"], "vcardArray": ["vcard", [["email", {}, "text", "private@example.com"]]]}],
            "nameservers": [{"ldhName": "ns1.example.com"}],
        }
        edit = AsyncMock()
        with patch.object(network_tools, "fetch_json", new=AsyncMock(return_value=data)) as fetch:
            await lookup_message("whois", "EXAMPLE.COM", edit)
        fetch.assert_awaited_once_with("https://rdap.org/domain/example.com")
        text = edit.call_args.args[0]
        for value in ("2020-01-01", "ns1.example.com", "Registrar &lt;Inc&gt;"):
            self.assertIn(value, text)
        self.assertNotIn("private@example.com", text)

    async def test_malformed_optional_fields_do_not_break_formatting(self):
        text = format_ip({"success": True, "connection": []}, "1.1.1.1", "en")
        self.assertIn("—", text)
        text = format_domain({"objectClassName": "domain", "entities": [None, {"roles": ["registrar"], "vcardArray": "bad"}], "nameservers": {}, "events": [{"eventAction": []}], "status": None}, "example.com", "en")
        self.assertIn("example.com", text)

    async def test_large_remote_fields_fit_telegram_and_are_escaped(self):
        data = {"objectClassName": "domain", "status": ["<x>" * 1000] * 100, "nameservers": [{"ldhName": "<x>" * 1000}] * 100}
        text = format_domain(data, "example.com", "vi")
        self.assertLess(len(text.encode("utf-16-le")) // 2, 4000)
        self.assertNotIn("<x>", text)

    async def test_rate_limits_missing_data_and_network_errors_are_safe(self):
        for error, expected in ((PublicHTTPError("http_status", 429), "giới hạn"), (PublicHTTPError("http_status", 404), "Không tìm thấy")):
            edit = AsyncMock()
            with patch.object(network_tools, "fetch_json", new=AsyncMock(side_effect=error)):
                await lookup_message("whois", "example.com", edit)
            self.assertIn(expected, edit.call_args.args[0])
        for error in (asyncio.TimeoutError(), network_tools.aiohttp.ClientError("private-token"), PublicHTTPError("invalid_response")):
            edit = AsyncMock()
            with patch.object(network_tools, "fetch_json", new=AsyncMock(side_effect=error)):
                await lookup_message("ip", "1.1.1.1", edit)
            self.assertNotIn("private-token", str(edit.call_args_list))
            self.assertIn("Chưa tra được", edit.call_args.args[0])

    async def test_ip_service_failure_is_reported_without_echoing_message(self):
        edit = AsyncMock()
        with patch.object(network_tools, "fetch_json", new=AsyncMock(return_value={"success": False, "message": "private-token"})):
            await lookup_message("ip", "1.1.1.1", edit)
        self.assertIn("Không tìm thấy", edit.call_args.args[0])
        self.assertNotIn("private-token", str(edit.call_args_list))

    async def test_cancellation_propagates(self):
        with patch.object(network_tools, "fetch_json", new=AsyncMock(side_effect=asyncio.CancelledError())):
            with self.assertRaises(asyncio.CancelledError):
                await lookup_message("ip", "1.1.1.1", AsyncMock())


if __name__ == "__main__":
    unittest.main()
