import base64
import importlib.util
import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

spec = importlib.util.spec_from_file_location('otp_broker', Path(__file__).with_name('otp_broker.py'))
otp_broker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(otp_broker)


def encoded(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip('=')


class MessageTests(unittest.TestCase):
    def test_extracts_code_from_nested_html(self):
        message = {'payload': {'headers': [{'name': 'Subject', 'value': 'Sign-in verification'}], 'parts': [
            {'mimeType': 'text/html', 'body': {'data': encoded('<p>Your verification code is <b>123456</b></p>')}}
        ]}}
        self.assertEqual(otp_broker.extract_code(message), '123456')

    def test_ignores_unlabelled_numbers(self):
        message = {'payload': {'headers': [], 'body': {'data': encoded('Message 123456 expires in 600 seconds')}}}
        self.assertIsNone(otp_broker.extract_code(message))


class StorageTests(unittest.TestCase):
    def test_private_json_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'private' / 'token.json'
            otp_broker.write_private_json(path, {'refresh_token': 'not-a-real-token'})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
            self.assertEqual(json.loads(path.read_text())['refresh_token'], 'not-a-real-token')


class FakeGmailClient(otp_broker.GmailClient):
    def __init__(self, messages):
        self.messages = messages
        self.used_message_ids = set()

    def api_json(self, path, query=None):
        if path == 'users/me/messages':
            return {'messages': [{'id': key} for key in self.messages]}
        return self.messages[path.rsplit('/', 1)[-1]]


class GmailSelectionTests(unittest.TestCase):
    def test_rejects_stale_and_reused_messages(self):
        stale = {'internalDate': '1000', 'payload': {'headers': [], 'body': {'data': encoded('Verification code: 111111')}}}
        fresh = {'internalDate': '50000', 'payload': {'headers': [], 'body': {'data': encoded('Verification code: 222222')}}}
        client = FakeGmailClient({'stale': stale, 'fresh': fresh})
        self.assertEqual(client.find_code('alias@example.com', 50_000), '222222')
        self.assertIsNone(client.find_code('alias@example.com', 50_000))


class BrokerServerTests(unittest.TestCase):
    class Client:
        def wait_for_code(self, recipient, after_ms):
            return '654321'

    def request(self, url, token, email):
        request = urllib.request.Request(
            url,
            data=json.dumps({'email': email, 'after_ms': 1}).encode(),
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
        )
        return urllib.request.urlopen(request).read()

    def test_allows_only_configured_recipient_and_bearer(self):
        with otp_broker.serve(self.Client(), {'allowed@example.com'}) as (url, token):
            self.assertEqual(json.loads(self.request(url, token, 'allowed@example.com'))['code'], '654321')
            with self.assertRaises(urllib.error.HTTPError) as denied_recipient:
                self.request(url, token, 'other@example.com')
            self.assertEqual(denied_recipient.exception.code, 400)
            with self.assertRaises(urllib.error.HTTPError) as denied_token:
                self.request(url, 'wrong', 'allowed@example.com')
            self.assertEqual(denied_token.exception.code, 404)


if __name__ == '__main__':
    unittest.main()
