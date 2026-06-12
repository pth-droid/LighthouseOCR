import unittest

from department_tagging_dialog import TaggingState


class TaggingStateTests(unittest.TestCase):
    def test_assign_sets_and_advances_to_next(self):
        s = TaggingState(["a.jpg", "b.jpg", "c.jpg"])
        self.assertEqual(s.current_filename(), "a.jpg")
        self.assertTrue(s.assign("BEP"))
        self.assertEqual(s.department_of("a.jpg"), "BEP")
        self.assertEqual(s.current_filename(), "b.jpg")

    def test_assign_normalizes_case(self):
        s = TaggingState(["a.jpg"])
        s.assign("bep")
        self.assertEqual(s.department_of("a.jpg"), "BEP")

    def test_invalid_dept_rejected(self):
        s = TaggingState(["a.jpg"])
        self.assertFalse(s.assign("XYZ"))
        self.assertIsNone(s.department_of("a.jpg"))
        self.assertEqual(s.current_filename(), "a.jpg")

    def test_advance_skips_already_assigned(self):
        s = TaggingState(["a.jpg", "b.jpg", "c.jpg"])
        s.goto(1)
        s.assign("BAR")          # b assigned -> advance to c
        self.assertEqual(s.current_filename(), "c.jpg")
        s.assign("BEP")          # c assigned -> wrap to a (still unassigned)
        self.assertEqual(s.current_filename(), "a.jpg")

    def test_assign_last_unassigned_stays_put(self):
        s = TaggingState(["a.jpg", "b.jpg"])
        s.assign("BEP")          # -> b
        s.assign("BAR")          # all assigned, stay on b
        self.assertEqual(s.current_filename(), "b.jpg")
        self.assertTrue(s.is_complete())

    def test_back_forward_goto_bounds(self):
        s = TaggingState(["a.jpg", "b.jpg"])
        s.back()                 # already at 0, no-op
        self.assertEqual(s.current_filename(), "a.jpg")
        s.forward()
        self.assertEqual(s.current_filename(), "b.jpg")
        s.forward()              # at end, no-op
        self.assertEqual(s.current_filename(), "b.jpg")
        s.goto(0)
        self.assertEqual(s.current_filename(), "a.jpg")
        s.goto(99)               # out of range, no-op
        self.assertEqual(s.current_filename(), "a.jpg")

    def test_is_complete_and_counts(self):
        s = TaggingState(["a.jpg", "b.jpg"])
        self.assertFalse(s.is_complete())
        self.assertEqual(s.remaining(), 2)
        s.assign("BEP")
        self.assertEqual(s.assigned_count(), 1)
        self.assertFalse(s.is_complete())
        s.assign("BAR")
        self.assertTrue(s.is_complete())
        self.assertEqual(s.remaining(), 0)

    def test_get_department_map_keyed_by_filename(self):
        s = TaggingState(["a.jpg", "b.jpg"])
        s.assign("BEP")
        s.assign("RANG")
        self.assertEqual(s.get_department_map(), {"a.jpg": "BEP", "b.jpg": "RANG"})

    def test_empty_state_is_not_complete(self):
        s = TaggingState([])
        self.assertFalse(s.is_complete())
        self.assertIsNone(s.current_filename())
        self.assertFalse(s.assign("BEP"))

    def test_rotation_defaults_to_zero(self):
        s = TaggingState(["a.jpg"])
        self.assertEqual(s.rotation_of("a.jpg"), 0)

    def test_rotate_right_and_left_wrap(self):
        s = TaggingState(["a.jpg"])
        s.rotate_right()
        self.assertEqual(s.rotation_of("a.jpg"), 90)
        s.rotate_right()
        s.rotate_right()
        s.rotate_right()
        self.assertEqual(s.rotation_of("a.jpg"), 0)   # 4x90 wraps
        s.rotate_left()
        self.assertEqual(s.rotation_of("a.jpg"), 270)

    def test_rotation_is_per_image(self):
        s = TaggingState(["a.jpg", "b.jpg"])
        s.rotate_right()                 # rotates a.jpg
        s.goto(1)
        s.rotate_left()                  # rotates b.jpg
        self.assertEqual(s.rotation_of("a.jpg"), 90)
        self.assertEqual(s.rotation_of("b.jpg"), 270)

    def test_rotate_noop_on_empty(self):
        s = TaggingState([])
        s.rotate_right()                 # no current image -> no error
        s.rotate_left()
        self.assertEqual(s.rotation_of("x.jpg"), 0)


if __name__ == "__main__":
    unittest.main()
