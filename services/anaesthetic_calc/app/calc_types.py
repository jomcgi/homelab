from dataclasses import dataclass
from enum import Enum
from typing import NamedTuple


class LocalAnaestheticDose(NamedTuple):
    drug: str
    concentration: str
    dose_in_ml: str


@dataclass
class Concentration:
    value: float


@dataclass
class MaxDose:
    value: float

    def __str__(self):
        return f"{self.value:.2f}mg/kg"


@dataclass
class Drug:
    name: str | None
    concentrations: list[Concentration] | None
    max_dose: MaxDose | None


LIDOCAINE = Drug(
    name="Lidocaine",
    concentrations=[Concentration(0.5), Concentration(1)],
    max_dose=MaxDose(4.5),
)

BUPIVACAINE = Drug(
    name="Bupivacaine",
    concentrations=[Concentration(0.25), Concentration(0.5)],
    max_dose=MaxDose(2),
)

ROPIVACAINE = Drug(
    name="Ropivacaine",
    concentrations=[Concentration(0.2), Concentration(0.75)],
    max_dose=MaxDose(3),
)


class LocalAnaestheticDrug(Enum):
    LIDOCAINE = LIDOCAINE
    BUPIVACAINE = BUPIVACAINE
    ROPIVACAINE = ROPIVACAINE
