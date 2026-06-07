import re
import unicodedata


def _clean(value):
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _dept_from_group(group):
    text = str(group or "").upper()
    for dept in ("BEP", "BAR", "BANH", "RANG"):
        if dept in text:
            return dept
    return None


def _parse_money_values(text):
    values = []
    for token in re.findall(r"\d[\d.,]{2,}", str(text or "")):
        cleaned = token.replace(".", "").replace(",", "")
        try:
            value = float(cleaned)
        except ValueError:
            continue
        if value >= 1000:
            values.append(value)
    return values


def _parse_totals(text):
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    total_keywords = ("tong cong", "thanh tien", "can thanh toan", "tong tien")
    for line in reversed(lines):
        clean_line = _clean(line)
        if any(keyword in clean_line for keyword in total_keywords):
            values = _parse_money_values(line)
            if values:
                return {"total_amount": values[-1]}
    values = _parse_money_values(text)
    return {"total_amount": max(values)} if values else {}


def _parse_date(text):
    match = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b", str(text or ""))
    if not match:
        return None
    day, month, year = match.groups()
    if len(year) == 2:
        year = "20" + year
    return f"{int(day):02d}/{int(month):02d}/{year}"


class BusinessKIE:
    def __init__(self, data_store):
        self.data_store = data_store

    def _extract_supplier(self, text):
        cleaned = _clean(text)
        for code, name in getattr(self.data_store, "suppliers_dict", {}).items():
            code_text = _clean(code)
            name_text = _clean(name)
            if code_text and re.search(rf"\b{re.escape(code_text)}\b", cleaned):
                return {
                    "supplier_name_code": str(code).strip(),
                    "supplier_name_raw": str(name).strip(),
                    "confidence": 0.95,
                }
            if name_text and name_text in cleaned:
                return {
                    "supplier_name_code": str(code).strip(),
                    "supplier_name_raw": str(name).strip(),
                    "confidence": 0.9,
                }
        return {"supplier_name_code": None, "supplier_name_raw": None, "confidence": 0.0}

    def _item_from_alias(self, alias, info):
        code = str((info or {}).get("code") or "").strip()
        record = getattr(self.data_store, "items_by_code", {}).get(code.lower(), {})
        unit = record.get("unit")
        units = (info or {}).get("units") or []
        if not unit and units:
            unit = units[0].get("unit")
        return {
            "item_code": code,
            "product_name": record.get("name") or alias,
            "unit": unit or None,
            "quantity": None,
            "unit_price": None,
            "total_price": None,
            "confidence": 0.88,
            "_group": record.get("group"),
        }

    def _extract_items(self, text):
        cleaned = _clean(text)
        seen = set()
        items = []

        for alias, info in getattr(self.data_store, "aliases_dict", {}).items():
            alias_key = _clean(alias)
            if alias_key and alias_key in cleaned:
                item = self._item_from_alias(alias, info)
                key = item.get("item_code") or item.get("product_name")
                if key not in seen:
                    seen.add(key)
                    items.append(item)

        if items:
            return items

        for name, record in getattr(self.data_store, "items_dict", {}).items():
            name_key = _clean(record.get("name") or name)
            if name_key and name_key in cleaned:
                key = record.get("code") or record.get("name")
                if key in seen:
                    continue
                seen.add(key)
                items.append({
                    "item_code": record.get("code"),
                    "product_name": record.get("name") or name,
                    "unit": record.get("unit"),
                    "quantity": None,
                    "unit_price": None,
                    "total_price": None,
                    "confidence": 0.75,
                    "_group": record.get("group"),
                })
        return items

    def extract(self, normalized_structure):
        text = normalized_structure.get("raw_text") or ""
        supplier = self._extract_supplier(text)
        items = self._extract_items(text)
        department = None
        for item in items:
            department = _dept_from_group(item.get("_group"))
            if department:
                break
        for item in items:
            item.pop("_group", None)

        return {
            "supplier": supplier,
            "transaction": {
                "department": department,
                "invoice_date": _parse_date(text),
            },
            "items": items,
            "totals": _parse_totals(text),
            "warnings": [],
        }
