from enum import Enum


class Graphic_Type(Enum):
    description: str

    TimesRegistering = (1, "Times Registering")
    Burndown = (2, "Burndown")
    def __new__(cls, value, description):
            obj = object.__new__(cls)
            obj._value_ = value
            obj.description = description
            return obj

    @classmethod
    def from_description(cls, description: str):
        for item in cls:
            if item.description == description:
                return item
        raise ValueError(f"Unknown description: {description}")
