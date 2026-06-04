def build_invoice_json(kie_result, confidence_score):
    supplier = kie_result.get("supplier", {}) or {}
    transaction = kie_result.get("transaction", {}) or {}
    totals = kie_result.get("totals", {}) or {}
    return {
        "document_info": {
            "recommended_model": "PPStructureV3",
            "invoice_type": "STRUCTURE_EXTRACTED",
            "confidence_score": float(round(confidence_score, 3)),
        },
        "supplier_info": {
            "supplier_name_raw": supplier.get("supplier_name_raw"),
            "supplier_name_code": supplier.get("supplier_name_code"),
            "tax_id": supplier.get("tax_id"),
        },
        "transaction_info": {
            "invoice_number": transaction.get("invoice_number"),
            "invoice_date": transaction.get("invoice_date"),
            "department": transaction.get("department"),
            "buyer_name": transaction.get("buyer_name"),
            "delivery_location": transaction.get("delivery_location"),
            "raw_discount_info": transaction.get("raw_discount_info"),
            "raw_shipping_fee_info": transaction.get("raw_shipping_fee_info"),
            "raw_payment_method": transaction.get("raw_payment_method"),
        },
        "items": [
            {
                "item_code": item.get("item_code"),
                "product_name": item.get("product_name"),
                "unit": item.get("unit"),
                "quantity": item.get("quantity"),
                "unit_price": item.get("unit_price"),
                "total_price": item.get("total_price"),
                "raw_vat_rate": item.get("raw_vat_rate"),
                "raw_vat_amount": item.get("raw_vat_amount"),
            }
            for item in (kie_result.get("items") or [])
        ],
        "totals": {
            "sub_total": totals.get("sub_total", 0),
            "vat_percentage": totals.get("vat_percentage", 0),
            "vat_amount": totals.get("vat_amount", 0),
            "total_amount": totals.get("total_amount", 0),
        },
        "_structure_pipeline": {
            "warnings": kie_result.get("warnings", []),
            "fallback_used": False,
        },
    }
