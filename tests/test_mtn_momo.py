from __future__ import annotations

import base64
import io
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

from backend.mtn_momo import MomoApiError, MomoClient, SANDBOX_BASE_URL


class MomoClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = {
            f"{product}_{key}": f"{product}-{key}"
            for product in ("collection", "disbursement")
            for key in ("subscription_key", "api_user", "api_key")
        }
        self.client = MomoClient(self.settings)

    def test_collection_uses_sandbox_auth_and_uganda_currency(self) -> None:
        responses = [
            io.BytesIO(b'{"access_token":"sandbox-token"}'),
            io.BytesIO(b""),
        ]
        reference_id = str(uuid4())

        with patch("backend.mtn_momo.urlopen", side_effect=responses) as open_url:
            self.client.request_to_pay(reference_id, 25_000, "+256772123456")

        token_request = open_url.call_args_list[0].args[0]
        payment_request = open_url.call_args_list[1].args[0]
        self.assertEqual(
            token_request.full_url,
            f"{SANDBOX_BASE_URL}/collection/token/",
        )
        self.assertEqual(
            token_request.get_header("Authorization"),
            "Basic "
            + base64.b64encode(b"collection-api_user:collection-api_key").decode(),
        )
        self.assertEqual(payment_request.full_url, f"{SANDBOX_BASE_URL}/collection/v1_0/requesttopay")
        self.assertEqual(payment_request.get_header("X-target-environment"), "sandbox")
        self.assertEqual(payment_request.get_header("X-reference-id"), reference_id)
        payload = json.loads(payment_request.data)
        self.assertEqual(payload["currency"], "UGX")
        self.assertEqual(payload["amount"], "25000")
        self.assertEqual(payload["payer"]["partyId"], "256772123456")

    def test_disbursement_status_uses_product_endpoint(self) -> None:
        responses = [
            io.BytesIO(b'{"access_token":"sandbox-token"}'),
            io.BytesIO(b'{"status":"SUCCESSFUL","amount":"25000","currency":"UGX"}'),
        ]
        reference_id = str(uuid4())

        with patch("backend.mtn_momo.urlopen", side_effect=responses) as open_url:
            result = self.client.transfer_status(reference_id)

        status_request = open_url.call_args_list[1].args[0]
        self.assertEqual(
            status_request.full_url,
            f"{SANDBOX_BASE_URL}/disbursement/v1_0/transfer/{reference_id}",
        )
        self.assertEqual(result["status"], "SUCCESSFUL")

    def test_missing_product_credentials_fail_without_network_call(self) -> None:
        client = MomoClient({})
        with patch("backend.mtn_momo.urlopen") as open_url:
            with self.assertRaises(MomoApiError):
                client.request_to_pay(str(uuid4()), 1000, "+256772123456")

        open_url.assert_not_called()

    def test_status_rejects_non_uuid_reference(self) -> None:
        with self.assertRaises(MomoApiError):
            self.client.collection_status("not-a-uuid")


if __name__ == "__main__":
    unittest.main()
