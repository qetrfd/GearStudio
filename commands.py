from PySide6.QtGui import QUndoCommand
from gear_math import GearSpec

class AddGearCmd(QUndoCommand):
    def __init__(self, window, spec: GearSpec, index: int | None = None):
        super().__init__("Add gear")
        self.w = window
        self.spec = spec
        self.index = index
        self._did = False

    def redo(self):
        if self.index is None:
            self.w._gear_specs.append(self.spec)
        else:
            self.w._gear_specs.insert(self.index, self.spec)
        self._did = True
        self.w._recompute(select_index=self.index if self.index is not None else len(self.w._gear_specs) - 1)

    def undo(self):
        if not self._did:
            return
        if self.index is None:
            self.w._gear_specs.pop()
        else:
            self.w._gear_specs.pop(self.index)
        self.w._recompute(select_index=min(self.index if self.index is not None else 0, len(self.w._gear_specs) - 1))

class RemoveGearCmd(QUndoCommand):
    def __init__(self, window, index: int):
        super().__init__("Remove gear")
        self.w = window
        self.index = index
        self.spec = None

    def redo(self):
        if 0 <= self.index < len(self.w._gear_specs):
            self.spec = self.w._gear_specs.pop(self.index)
        self.w._recompute(select_index=min(self.index, len(self.w._gear_specs) - 1))

    def undo(self):
        if self.spec is None:
            return
        self.w._gear_specs.insert(self.index, self.spec)
        self.w._recompute(select_index=self.index)

class EditGearCmd(QUndoCommand):
    def __init__(self, window, index: int, new_spec: GearSpec):
        super().__init__("Edit gear")
        self.w = window
        self.index = index
        self.new_spec = new_spec
        self.old_spec = None

    def redo(self):
        if 0 <= self.index < len(self.w._gear_specs):
            self.old_spec = self.w._gear_specs[self.index]
            self.w._gear_specs[self.index] = self.new_spec
        self.w._recompute(select_index=self.index)

    def undo(self):
        if self.old_spec is None:
            return
        self.w._gear_specs[self.index] = self.old_spec
        self.w._recompute(select_index=self.index)

class AssignMotorCmd(QUndoCommand):
    def __init__(self, window, index: int, rpm: float | None):
        super().__init__("Assign motor")
        self.w = window
        self.index = index
        self.new = rpm
        self.old = None

    def redo(self):
        if 0 <= self.index < len(self.w._gear_specs):
            self.old = self.w._gear_specs[self.index].motor_rpm
            self.w._gear_specs[self.index].motor_rpm = self.new
        self.w._recompute(select_index=self.index)

    def undo(self):
        if 0 <= self.index < len(self.w._gear_specs):
            self.w._gear_specs[self.index].motor_rpm = self.old
        self.w._recompute(select_index=self.index)

class ClearTrainCmd(QUndoCommand):
    def __init__(self, window):
        super().__init__("Clear train")
        self.w = window
        self.backup = None

    def redo(self):
        self.backup = list(self.w._gear_specs)
        self.w._gear_specs.clear()
        self.w._recompute(select_index=-1)

    def undo(self):
        if self.backup is None:
            return
        self.w._gear_specs = list(self.backup)
        self.w._recompute(select_index=0 if self.w._gear_specs else -1)