import unittest

from core_excel_mapper import _should_route_unmapped_to_chiphi


class ExcelRoutingTests(unittest.TestCase):
    def test_unmapped_item_stays_in_pnmh_when_invoice_has_mapped_inventory_items(self):
        self.assertFalse(_should_route_unmapped_to_chiphi(
            item_unmapped=True,
            supplier_known=True,
            mapping_risky=False,
            map_score=0.0,
            invoice_has_mapped_items=True,
        ))

    def test_unmapped_item_can_route_to_chiphi_when_invoice_has_no_mapped_inventory_items(self):
        self.assertTrue(_should_route_unmapped_to_chiphi(
            item_unmapped=True,
            supplier_known=True,
            mapping_risky=False,
            map_score=0.0,
            invoice_has_mapped_items=False,
        ))

    def test_unknown_supplier_keeps_unmapped_item_in_pnmh(self):
        self.assertFalse(_should_route_unmapped_to_chiphi(
            item_unmapped=True,
            supplier_known=False,
            mapping_risky=False,
            map_score=0.0,
            invoice_has_mapped_items=False,
        ))


if __name__ == "__main__":
    unittest.main()
