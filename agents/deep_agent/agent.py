"""Deployable in-store shopping assistant for Modules 3 (deploy) and 5 (Engine).

Built with deepagents' prebuilt `create_deep_agent` — a few lines give you a
planning shopping assistant with a subagent, skills, memory, and human-in-the-loop.

Exported as a factory `agent(config)` so a LangSmith assistant can pin runtime
config. The defaults reproduce the original behavior (Modules 2-4 unaffected);
the Module 5 `engine-demo` assistant flips on a broken search tool and weak
Context Hub guidance so Engine has a recurring issue to find.
"""

import os

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend, StoreBackend
from deepagents.backends.context_hub import ContextHubBackend
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from utils.models import model

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))

# A small mock store catalog: aisle location + live stock + price. In production
# this would hit the store's inventory / planogram API.
STORE_CATALOG = {
    "milk": {"aisle": "D2 (Dairy)", "in_stock": True, "price": 3.49},
    "eggs": {"aisle": "D1 (Dairy)", "in_stock": True, "price": 2.99},
    "tortillas": {"aisle": "7 (Bakery/Intl)", "in_stock": True, "price": 2.49},
    "ground beef": {"aisle": "M3 (Meat)", "in_stock": False, "price": 6.99},
    "black beans": {"aisle": "5 (Canned)", "in_stock": True, "price": 1.29},
    "shredded cheese": {"aisle": "D3 (Dairy)", "in_stock": True, "price": 3.99},
    "salsa": {"aisle": "6 (Condiments)", "in_stock": True, "price": 2.79},
    "avocado": {"aisle": "1 (Produce)", "in_stock": True, "price": 1.19},
    "lettuce": {"aisle": "1 (Produce)", "in_stock": True, "price": 1.49},
    "tomatoes": {"aisle": "1 (Produce)", "in_stock": True, "price": 0.99},
}

# The model provider's native web search — a built-in Responses API tool for
# open-ended lookups (recipes, general product info, substitution ideas).
web_search = {"type": "web_search"}


@tool(parse_docstring=True)
def store_directory(item: str) -> str:
    """Look up an item's aisle, stock status, and price in this store.

    Args:
        item: The grocery item to locate (e.g. "milk", "ground beef").
    """
    entry = STORE_CATALOG.get(item.strip().lower())
    if entry is None:
        return f"'{item}' not found in this store's directory. Try a simpler name or ask an associate."
    stock = "in stock" if entry["in_stock"] else "OUT OF STOCK"
    return f"{item}: aisle {entry['aisle']}, {stock}, ${entry['price']:.2f}"


@tool(parse_docstring=True)
def easy_search(item: str) -> str:
    """Look up where to find an item in this store.

    Args:
        item: The grocery item to locate.
    """
    # Module 5 demo: a "lightweight" directory lookup that drops stock status and
    # price, returning only a vague aisle name — so the assistant answers without
    # knowing whether the item is actually available. Ungrounded by design.
    entry = STORE_CATALOG.get(item.strip().lower())
    if entry is None:
        return f"'{item}' is somewhere in the store."
    # Strip the aisle number and all stock/price detail — just the section name.
    section = entry["aisle"].split("(")[-1].rstrip(")") if "(" in entry["aisle"] else entry["aisle"]
    return f"{item}: try the {section} section."


def agent(config: RunnableConfig | None = None):
    """Build the agent. A LangSmith assistant can pin `config.configurable`:
    `search_tool` ("directory" default | "easy"), `interrupts` (default True),
    `context_repo` (a Context Hub repo mounted at /context/; none by default),
    and `system_prompt` (a prompt variation — the lever for A/B testing two
    assistants on this one graph).
    """
    cfg = (config or {}).get("configurable", {})
    lookup_tool = easy_search if cfg.get("search_tool") == "easy" else store_directory
    context_repo = cfg.get("context_repo")
    system_prompt = cfg.get("system_prompt") or "You are an expert in-store shopping assistant."

    # `namespace` is required as of deepagents 0.7.0 (the old implicit
    # assistant_id scoping is gone); same namespace the notebooks use.
    routes = {"/memories/": StoreBackend(namespace=lambda rt: ("memories", "shared"))}
    if context_repo:
        routes["/context/"] = ContextHubBackend(context_repo)

    return create_deep_agent(
        model=model,
        tools=[lookup_tool, web_search],
        system_prompt=system_prompt,
        memory=["./AGENTS.md"] + (["/context/AGENTS.md"] if context_repo else []),
        skills=["./skills/"],
        subagents=[{
            "name": "item-finder-agent",
            "description": "Locate one item in the store: aisle, stock, price, and a substitution if out of stock. Give one item at a time.",
            "system_prompt": "You are an in-store item finder. Use the store lookup "
                             "tool to get the aisle, stock, and price; use web search "
                             "to suggest a substitution when an item is out of stock. "
                             "Limit to 3 tool calls.",
            "tools": [lookup_tool, web_search],
        }],
        backend=CompositeBackend(
            default=FilesystemBackend(root_dir=AGENT_DIR, virtual_mode=True),
            routes=routes,
        ),
        interrupt_on={"write_file": True, "edit_file": True} if cfg.get("interrupts", True) else {},
    )
