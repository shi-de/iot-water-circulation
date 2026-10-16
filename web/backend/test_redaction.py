import json
import unittest

from main import redact_payload


class RedactionTest(unittest.TestCase):
    def test_credential_like_fields_are_redacted_recursively(self):
        payload = {"password": "secret", "nested": {"token": "abc", "flow": 0.5}}

        redacted = redact_payload(payload)

        self.assertEqual(redacted["password"], "[redacted]")
        self.assertEqual(redacted["nested"]["token"], "[redacted]")
        self.assertEqual(redacted["nested"]["flow"], 0.5)
        self.assertNotIn("secret", json.dumps(redacted))


if __name__ == "__main__":
    unittest.main()
