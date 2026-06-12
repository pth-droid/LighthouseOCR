"""Pre-scan department tagging: headless TaggingState core + Qt dialog view.

The TaggingState class has no Qt dependency so it is unit-testable. The
DepartmentTaggingDialog (added in a later task) is a thin view over it.
"""

from departments import VALID_DEPARTMENTS


class TaggingState:
    """Ordered list of image filenames + their department assignments."""

    def __init__(self, filenames):
        self.filenames = list(filenames)
        self.assignments = {}          # filename -> dept (UPPER, valid only)
        self.current_index = 0

    @property
    def total(self):
        return len(self.filenames)

    def current_filename(self):
        if not self.filenames:
            return None
        return self.filenames[self.current_index]

    def _next_unassigned_index(self):
        n = self.total
        for offset in range(1, n + 1):
            idx = (self.current_index + offset) % n
            if self.filenames[idx] not in self.assignments:
                return idx
        return None

    def assign(self, dept):
        dept = str(dept or "").strip().upper()
        if dept not in VALID_DEPARTMENTS:
            return False
        fn = self.current_filename()
        if fn is None:
            return False
        self.assignments[fn] = dept
        nxt = self._next_unassigned_index()
        if nxt is not None:
            self.current_index = nxt
        return True

    def back(self):
        if self.current_index > 0:
            self.current_index -= 1

    def forward(self):
        if self.current_index < self.total - 1:
            self.current_index += 1

    def goto(self, index):
        if 0 <= index < self.total:
            self.current_index = index

    def department_of(self, filename):
        return self.assignments.get(filename)

    def assigned_count(self):
        return len(self.assignments)

    def remaining(self):
        return self.total - self.assigned_count()

    def is_complete(self):
        return self.total > 0 and all(
            fn in self.assignments for fn in self.filenames
        )

    def get_department_map(self):
        return dict(self.assignments)
