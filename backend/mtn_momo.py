from __future__ import annotations

import base64
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID

SANDBOX_BASE_URL = "https://sandbox.momodeveloper.mtn.com"


class MomoApiError(Exception):
    pass


class MomoClient:
    def __init__(self, settings: dict, timeout: int = 15) -> None:
        self.settings = settings
        self.timeout = timeout

    def is_configured(self, product: str) -> bool:
        return all(
            self.settings.get(f"{product}_{key}")
            for key in ("subscription_key", "api_user", "api_key")
        )

    def request_to_pay(self, reference_id: str, amount: int, phone: str) -> None:
        self._submit(
            "collection",
            "POST",
            "/collection/v1_0/requesttopay",
            reference_id,
            {
                "amount": str(amount),
                "currency": "UGX",
                "externalId": reference_id,
                "payer": {"partyIdType": "MSISDN", "partyId": phone.lstrip("+")},
                "payerMessage": "CampusFlow allowance deposit",
                "payeeNote": "CampusFlow allowance deposit",
            },
        )

    def transfer(self, reference_id: str, amount: int, phone: str) -> None:
        self._submit(
            "disbursement",
            "POST",
            "/disbursement/v1_0/transfer",
            reference_id,
            {
                "amount": str(amount),
                "currency": "UGX",
                "externalId": reference_id,
                "payee": {"partyIdType": "MSISDN", "partyId": phone.lstrip("+")},
                "payerMessage": "CampusFlow allowance payout",
                "payeeNote": "CampusFlow allowance payout",
            },
        )

    def collection_status(self, reference_id: str) -> dict:
        return self._status("collection", "requesttopay", reference_id)

    def transfer_status(self, reference_id: str) -> dict:
        return self._status("disbursement", "transfer", reference_id)

    def _submit(
        self,
        product: str,
        method: str,
        path: str,
        reference_id: str,
        payload: dict,
    ) -> None:
        self._request(
            product,
            method,
            path,
            reference_id=reference_id,
            payload=payload,
        )

    def _status(self, product: str, operation: str, reference_id: str) -> dict:
        try:
            UUID(reference_id)
        except ValueError as error:
            raise MomoApiError("Invalid MTN MoMo reference ID.") from error
        return self._request(
            product,
            "GET",
            f"/{product}/v1_0/{operation}/{reference_id}",
        )

    def _request(
        self,
        product: str,
        method: str,
        path: str,
        reference_id: str | None = None,
        payload: dict | None = None,
    ) -> dict:
        if not self.is_configured(product):
            raise MomoApiError(f"MTN {product} sandbox credentials are not configured.")

        api_user = self.settings[f"{product}_api_user"]
        api_key = self.settings[f"{product}_api_key"]
        subscription_key = self.settings[f"{product}_subscription_key"]
        credentials = base64.b64encode(f"{api_user}:{api_key}".encode()).decode("ascii")
        token = self._send(
            Request(
                f"{SANDBOX_BASE_URL}/{product}/token/",
                method="POST",
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Ocp-Apim-Subscription-Key": subscription_key,
                    "X-Target-Environment": "sandbox",
                },
            )
        )
        if not isinstance(token, dict) or not token.get("access_token"):
            raise MomoApiError(f"MTN {product} sandbox returned no access token.")

        headers = {
            "Authorization": f"Bearer {token['access_token']}",
            "Ocp-Apim-Subscription-Key": subscription_key,
            "X-Target-Environment": "sandbox",
        }
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            headers["X-Reference-Id"] = str(UUID(reference_id))
            data = json.dumps(payload).encode("utf-8")
        return self._send(
            Request(
                f"{SANDBOX_BASE_URL}{path}",
                data=data,
                headers=headers,
                method=method,
            )
        )

    def _send(self, request: Request) -> dict:
        try:
            with urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except HTTPError as error:
            raise MomoApiError(
                f"MTN MoMo sandbox returned HTTP {error.code}."
            ) from error
        except URLError as error:
            raise MomoApiError(
                "Could not connect to the MTN MoMo sandbox."
            ) from error
        if not body:
            return {}
        try:
            result = json.loads(body)
        except json.JSONDecodeError as error:
            raise MomoApiError(
                "MTN MoMo sandbox returned an invalid response."
            ) from error
        if not isinstance(result, dict):
            raise MomoApiError("MTN MoMo sandbox returned an invalid response.")
        return result
