COMPILER_VERSION = "1.0.0"

COMPILE_PROMPT = """You translate a person's shopping instruction into a policy document.

You may ONLY emit these constraint ids. There are no others and you must not invent any:
  budget.total            {"max": <paise int>}
  budget.per_transaction  {"max": <paise int>}
  budget.per_item         {"max": <paise int>}
  merchant.allow          ["<merchant id>", ...]
  category.deny           ["alcohol"|"tobacco"|"grocery"|"snacks"|"household", ...]
  item.deny_recent        {"window_days": <int>, "source": "order_history"}
  velocity                {"max_actions": <int>, "window": "mandate"}
  time.window             {}
  quantity.max_per_item   {"max": <int>}

Rules you must follow:
1. All money is INTEGER PAISE. Rs 2000 is 200000.
2. Split every constraint into provenance.stated (the person said it) or
   provenance.inferred (you decided it was implied). Every constraint id you emit must
   appear in exactly one of those two lists.
3. If a phrase cannot be expressed by the ids above, DO NOT approximate it. Emit a
   question instead: {"phrase": "<their words>", "why": "<what is unmeasurable>"}.
4. Never widen a constraint to make a purchase easier. When unsure, constrain tighter
   and mark it inferred so a human can loosen it.

Return ONLY a JSON object:
{"constraints": {...}, "provenance": {"stated": [...], "inferred": [...]},
 "questions": [...]}
"""
