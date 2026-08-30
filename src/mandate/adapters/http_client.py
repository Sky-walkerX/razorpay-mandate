"""HTTP Client adapter for standalone Gateway daemon over wire."""
from datetime import datetime

import httpx

from mandate.gateway.action import Proposal, ProposalItem
from mandate.gateway.core import Decision
from mandate.gateway.state import Verdict


class HttpClient:
    def __init__(self, base_url: str = "http://localhost:8000", token: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._client = httpx.Client(base_url=self.base_url, timeout=10.0)

    def call(self, name: str, args: dict, now: datetime | None = None) -> Decision:
        if name != "create_order":
            raise ValueError(f"unknown tool {name}")

        items = [ProposalItem(sku=i["sku"], qty=int(i["qty"])) for i in args["items"]]
        prop = Proposal(merchant=args["merchant"], items=items)

        headers = {"Authorization": f"Bearer {self.token}"}
        resp = self._client.post("/v1/orders", json=prop.model_dump(mode="json"), headers=headers)

        if resp.status_code == 401 or resp.status_code == 403:
            data = resp.json()
            return Decision(
                verdict=Verdict.DENY,
                clause_id="authentication",
                message=f"{data.get("error")}: {data.get("detail", "")}",
                executed=False,
            )

        if not resp.is_success:
            return Decision(
                verdict=Verdict.DENY,
                clause_id="transport",
                message=f"HTTP {resp.status_code}: {resp.text}",
                executed=False,
            )

        return Decision(**resp.json())
