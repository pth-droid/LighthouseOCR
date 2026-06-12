"""Shared department constants and prompt helpers.

Kept dependency-free (no Qt, no heavy imports) so both the Qt tagging dialog
and the headless OCR pipeline can import it.
"""

VALID_DEPARTMENTS = ("BEP", "BAR", "BANH", "RANG")


def department_prompt_line(dept) -> str:
    """Return a one-block LLM prompt prefix telling the model the invoice's
    department, or "" when dept is not one of the 4 valid codes."""
    dept = str(dept or "").strip().upper()
    if dept not in VALID_DEPARTMENTS:
        return ""
    return (
        "DEPARTMENT_CONTEXT:\n"
        f"Hóa đơn này thuộc bộ phận [{dept}]. "
        "Ưu tiên đọc tên hàng theo nhóm hàng của bộ phận này.\n\n"
    )
