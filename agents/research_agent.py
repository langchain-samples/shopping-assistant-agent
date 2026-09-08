"""Shared in-store shopping assistant used by Module 2 (Deep Agents) and
Module 3 (LangSmith).

This is the minimal useful Deep Agent: an item-finder subagent + a store
directory tool + native web search + a checkpointer. It deliberately omits HITL
and FilesystemBackend so that evaluation runs in the LangSmith module don't
pause or leak files to disk.

Module 2 builds up to this agent step-by-step in the notebook. This file
packages the same pattern so the LangSmith module can import it directly:

    from agents.research_agent import build_shopping_agent
    agent = build_shopping_agent()

The deployable production agent lives in `agents/deep_agent/agent.py`; this is
the lightweight, eval-friendly sibling that shares the same theme and tools.
"""

from __future__ import annotations

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend
from deepagents.backends.context_hub import ContextHubBackend
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver

from utils.models import model as default_model

# --------------------------------------------------------------------------- #
# Mock store catalog. In production these tools would hit the store's inventory
# / planogram / pricing APIs; here a small in-memory dict keeps the workshop
# deterministic and offline-friendly. Each tool is a read-only lookup over this
# dict — no eval, no shell, no external calls.
# --------------------------------------------------------------------------- #
STORE_CATALOG: dict[str, dict] = {
    "milk":            {"aisle": "D2 (Dairy)",        "in_stock": True,  "price": 3.49, "sub": "oat milk"},
    "eggs":            {"aisle": "D1 (Dairy)",        "in_stock": True,  "price": 2.99, "sub": "egg substitute"},
    "tortillas":       {"aisle": "7 (Bakery/Intl)",   "in_stock": True,  "price": 2.49, "sub": "corn tortillas"},
    "ground beef":     {"aisle": "M3 (Meat)",         "in_stock": False, "price": 6.99, "sub": "ground turkey"},
    "black beans":     {"aisle": "5 (Canned)",        "in_stock": True,  "price": 1.29, "sub": "pinto beans"},
    "shredded cheese": {"aisle": "D3 (Dairy)",        "in_stock": True,  "price": 3.99, "sub": "queso fresco"},
    "salsa":           {"aisle": "6 (Condiments)",    "in_stock": True,  "price": 2.79, "sub": "pico de gallo"},
    "avocado":         {"aisle": "1 (Produce)",       "in_stock": True,  "price": 1.19, "sub": "guacamole cup"},
    "lettuce":         {"aisle": "1 (Produce)",       "in_stock": False, "price": 1.49, "sub": "shredded cabbage"},
    "tomatoes":        {"aisle": "1 (Produce)",       "in_stock": True,  "price": 0.99, "sub": "canned diced tomatoes"},
    "rice":            {"aisle": "4 (Grains)",        "in_stock": True,  "price": 2.19, "sub": "quinoa"},
    "chicken breast":  {"aisle": "M1 (Meat)",         "in_stock": True,  "price": 5.49, "sub": "chicken thighs"},
}


def _entry(item: str) -> dict | None:
    """Look up a catalog entry by a normalized item name (read-only)."""
    if not isinstance(item, str):
        return None
    return STORE_CATALOG.get(item.strip().lower())


@tool(parse_docstring=True)
def store_directory(item: str) -> str:
    """Look up an item's aisle, stock status, and price in this store.

    Args:
        item: The grocery item to locate (e.g. "milk", "ground beef").
    """
    entry = _entry(item)
    if entry is None:
        return f"'{item}' not found in this store's directory. Try a simpler name or ask an associate."
    stock = "in stock" if entry["in_stock"] else "OUT OF STOCK"
    return f"{item}: aisle {entry['aisle']}, {stock}, ${entry['price']:.2f}"


@tool(parse_docstring=True)
def check_stock(item: str) -> str:
    """Check whether an item is currently in stock at this store.

    Args:
        item: The grocery item to check.
    """
    entry = _entry(item)
    if entry is None:
        return f"'{item}' is not carried at this store."
    return f"{item}: {'in stock' if entry['in_stock'] else 'OUT OF STOCK'}"


@tool(parse_docstring=True)
def price_lookup(item: str) -> str:
    """Look up the shelf price of an item at this store.

    Args:
        item: The grocery item to price.
    """
    entry = _entry(item)
    if entry is None:
        return f"No price on file for '{item}'."
    return f"{item}: ${entry['price']:.2f}"


@tool(parse_docstring=True)
def find_substitution(item: str) -> str:
    """Suggest one in-store substitution for an item that's out of stock.

    Args:
        item: The out-of-stock grocery item to substitute.
    """
    entry = _entry(item)
    if entry is None:
        return f"No substitution on file for '{item}'."
    return f"{item}: try {entry['sub']} instead."


# The model provider's native web search — a built-in Responses API tool for
# open-ended lookups (recipes, general product info). Passed as a dict, so it
# runs server-side with no custom body to maintain.
web_search = {"type": "web_search"}

_SHOPPING_TOOLS = [store_directory, check_stock, price_lookup, find_substitution, web_search]


def build_shopping_agent(model=None, context_repo: str | None = None):
    """Return a fresh in-store shopping deep agent.

    Each call returns a new agent with a fresh checkpointer, so eval runs don't
    share state with each other.

    Args:
        model: Optional chat model to power the agent (defaults to the workshop
            model from ``utils.models``). Used by the model-comparison section.
        context_repo: Optional LangSmith Context Hub repo. When set, the agent's
            operating manual and skills are mounted from ``/context/`` (the Hub)
            instead of the local ``agents/research_agent`` checkout.
    """
    chat_model = model or default_model

    item_finder_subagent = {
        "name": "item-finder-agent",
        "description": (
            "Locate one item in the store: aisle, stock, price, and a substitution "
            "if it's out of stock. Give one item at a time."
        ),
        "system_prompt": (
            "You are an in-store item finder. Use the store tools to get the aisle, "
            "stock status, and price; use find_substitution or web search only when an "
            "item is out of stock. Report concisely. Limit to 3 tool calls."
        ),
        "tools": _SHOPPING_TOOLS,
    }

    kwargs = {}
    if context_repo:
        # Mount the Context Hub repo at /context/ and read the manual + skills
        # from there instead of the local checkout.
        # Mount the Hub repo at /context/ (a StateBackend handles scratch space,
        # matching the deployable agent's CompositeBackend pattern).
        kwargs["backend"] = CompositeBackend(
            default=StateBackend(),
            routes={"/context/": ContextHubBackend(context_repo)},
        )
        kwargs["memory"] = ["/context/AGENTS.md"]
        kwargs["skills"] = ["/context/skills/"]

    return create_deep_agent(
        model=chat_model,
        tools=_SHOPPING_TOOLS,
        system_prompt=(
            "You are an expert in-store shopping assistant. Delegate per-item lookups "
            "to the item-finder-agent, then assemble an aisle-ordered route and flag "
            "anything out of stock."
        ),
        subagents=[item_finder_subagent],
        checkpointer=MemorySaver(),
        **kwargs,
    )
