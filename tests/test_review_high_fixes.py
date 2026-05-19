import sys
from types import SimpleNamespace

sys.path.insert(0, ".")

PASS = 0
FAIL = 0


def check(label, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}" + (f" | {detail}" if detail else ""))


def test_llm_map_items_raises_when_google_genai_missing():
    import core_excel_mapper as m

    old_genai = m.genai
    old_types = m.types
    m.genai = None
    m.types = None
    try:
        raised = False
        try:
            m._llm_map_items(
                ["item-a"],
                object(),
                "api-key",
                candidates_by_item={"item-a": [{"name": "candidate-a"}]},
            )
        except RuntimeError as e:
            raised = "google-genai SDK is not installed" in str(e)
        check("core_excel_mapper._llm_map_items missing SDK raises RuntimeError", raised)
    finally:
        m.genai = old_genai
        m.types = old_types


def test_generate_with_fallback_skips_config_when_types_missing():
    import core_llm_client as c

    old_types = c.types
    c.types = None

    calls = {}

    class Models:
        def generate_content(self, **kwargs):
            calls.update(kwargs)
            return SimpleNamespace(text='{"ok": true}', usage_metadata=None)

    class DataStore:
        def should_use_minimal_thinking(self, *args, **kwargs):
            return True

    client = SimpleNamespace(models=Models())
    try:
        raw, _, _ = c.generate_with_fallback(
            client=client,
            models_to_try=[{"name": "m", "label": "M", "is_primary": True}],
            contents_fn=lambda _: ["prompt"],
            data_store=DataStore(),
            rate_bucket_fn=lambda _: "flash",
            base_wait_fn=lambda _: 1,
        )
        check("generate_with_fallback returns raw text", raw == '{"ok": true}', f"raw={raw}")
        check("generate_with_fallback passes config=None when types missing", calls.get("config") is None)
    finally:
        c.types = old_types


def test_llm_calculator_init_raises_without_genai():
    import module_calculator as m

    old_genai = m.genai
    m.genai = None
    try:
        raised = False
        try:
            m.LLMCalculator("api-key", object())
        except RuntimeError as e:
            raised = "google-genai SDK is not installed" in str(e)
        check("LLMCalculator init raises when SDK missing", raised)
    finally:
        m.genai = old_genai


if __name__ == "__main__":
    print("=" * 60)
    print("TEST: review HIGH-priority dependency branches")
    print("=" * 60)
    test_llm_map_items_raises_when_google_genai_missing()
    test_generate_with_fallback_skips_config_when_types_missing()
    test_llm_calculator_init_raises_without_genai()
    print("\n" + "=" * 60)
    total = PASS + FAIL
    print(f"RESULT: {PASS}/{total} passed | {FAIL} failed")
    if FAIL:
        sys.exit(1)
    print("ALL review HIGH-priority tests PASSED")
    print("=" * 60)
