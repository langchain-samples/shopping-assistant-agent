---
name: store-route
description: Turn a shopping list into an aisle-ordered walking route. Use this skill when asked for a store route, to organize a list for shopping, or to plan an efficient path through the store.
---

# Store Route Skill

## Format

- **Header**: Start with the store name and the item count
- **Route**: Group items by aisle, in ascending aisle order (Produce first, checkout last)
- For each item, show: name, aisle, price, and a `[ ]` checkbox
- **Out of stock**: Put unavailable items in their own section, each with one suggested substitution
- Keep it scannable on a phone while walking

## Tone

- Concise and practical — the shopper is reading it mid-trip
- Lead with what to grab and where, not commentary

## Rules

- Never invent an aisle or a price — use what the store lookup returned
- If an item's location is unknown, say so and suggest asking an associate
- Flag common allergens next to relevant items
