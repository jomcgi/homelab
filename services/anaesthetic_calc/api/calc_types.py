"""Drug Types for calculator API"""

from enum import Enum

from pydantic import BaseModel


class Drug(BaseModel):
    """Base class for Drugs"""

    name: str
    max_dose: float

    def max_dose_in_mg(self, weight: float):
        """Calculate max drug dose in mg"""
        return self.max_dose * weight


LIDOCAINE = Drug(name="Lidocaine", max_dose=3.0)

BUPIVACAINE = Drug(name="Bupivacaine", max_dose=2.0)


class LocalAnaestheticDrug(Enum):
    """Enum with Local Anaesthetic Drugs"""

    LIDOCAINE = LIDOCAINE
    BUPIVACAINE = BUPIVACAINE


class DrugDose(BaseModel):
    """Drug Dose base class"""

    drug_name: str
    concentration: float
    dose_in_ml: float

    @property
    def drug(self) -> Drug:
        return LocalAnaestheticDrug[self.drug_name.upper()].value

    def __str__(self):
        return f"{self.drug.name} {self.concentration}% {self.dose_in_ml}ml"

    def max_dose_in_ml(self, weight: float):
        """Calculate max dose in ml"""
        max_in_mg = self.drug.max_dose_in_mg(weight)
        return max_in_mg / 10 * 1 / self.concentration

    def portion_of_max_dose(self, weight: float):
        """Calculate portion of max dose this dose represents"""
        return self.dose_in_ml / self.max_dose_in_ml(weight)


class UnsafeDoseError(ValueError):
    """Error to raise when combined dose exceeds safe levels"""


class Patient(BaseModel):
    """Patient information"""

    weight: float
    doses: list[DrugDose]

    def _validate_doses_are_safe(self):
        doses_given = sum(dose.portion_of_max_dose(self.weight) for dose in self.doses)
        if doses_given > 1:
            raise UnsafeDoseError(
                f"Doses given exceed safe levels for patient. Doses: {self.doses}"
            )

    def add_dose(self, dose: DrugDose):
        """Add dose for Patient"""
        self.doses.append(dose)
        self._validate_doses_are_safe()
