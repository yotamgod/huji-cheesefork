from enum import IntEnum


class Semester(IntEnum):
    A = 1
    B = 2

    @classmethod
    def from_string(cls, string):
        if 'a' == string:
            return Semester.A
        if 'b' == string:
            return Semester.B
