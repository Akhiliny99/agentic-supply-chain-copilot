
import os
from dataclasses import dataclass
from typing import Callable

import httpx

ERP_BASE_URL = os.getenv("ERP_BASE_URL", "http://localhost:8001")


@dataclass
class Tool:
    name: str
    description: str
    fn: Callable
    requires_scope: str  


class PermissionError_(Exception):
    pass


def _get_inventory(sku: str) -> dict:
    return httpx.get(f"{ERP_BASE_URL}/inventory/{sku}", timeout=10).json()


def _get_orders(sku: str) -> dict:
    return httpx.get(f"{ERP_BASE_URL}/orders/{sku}", timeout=10).json()


def _get_pricing(sku: str) -> dict:
    return httpx.get(f"{ERP_BASE_URL}/pricing/{sku}", timeout=10).json()


def _update_pricing(sku: str, new_price: float, reason: str) -> dict:
    resp = httpx.post(
        f"{ERP_BASE_URL}/pricing/{sku}",
        json={"new_price": new_price, "reason": reason},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


TOOL_REGISTRY: dict[str, Tool] = {
    "get_inventory": Tool("get_inventory", "Read current stock level for a SKU", _get_inventory, "read"),
    "get_orders": Tool("get_orders", "Read order/sales history for a SKU", _get_orders, "read"),
    "get_pricing": Tool("get_pricing", "Read current price and cost for a SKU", _get_pricing, "read"),
    "update_pricing": Tool("update_pricing", "Write a new price for a SKU", _update_pricing, "write"),
}


AGENT_SCOPES: dict[str, list[str]] = {
    "forecaster": ["get_inventory", "get_orders"],
    "pricer": ["get_pricing", "get_orders", "update_pricing"],
    "supply_optimizer": ["get_inventory", "get_orders"],
    "moderator": ["get_inventory", "get_orders", "get_pricing"],  
}


def call_tool(agent_name: str, tool_name: str, **kwargs) -> dict:
    allowed = AGENT_SCOPES.get(agent_name, [])
    if tool_name not in allowed:
        raise PermissionError_(
            f"Agent '{agent_name}' is not scoped for tool '{tool_name}'. "
            f"Allowed: {allowed}"
        )
    tool = TOOL_REGISTRY[tool_name]
    return tool.fn(**kwargs)
