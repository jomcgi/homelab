from functools import lru_cache
from calc_types import (
    LocalAnaestheticDose,
    LocalAnaestheticDrug,
)


@lru_cache
def calculate_max_drug_dose(
    patient_weight: float, drug_input: str, drug_concentration: float
) -> float:
    anaesthetic_drug = LocalAnaestheticDrug[drug_input].value
    return (
        anaesthetic_drug.max_dose.value * patient_weight / 10 * 1 / drug_concentration
    )


def calculate_percentage_of_max_dose(
    dose: LocalAnaestheticDose, patient_weight: float
) -> float:
    return float(dose.dose_in_ml) / calculate_max_drug_dose(
        patient_weight, dose.drug, float(dose.concentration)
    )


def proportion_of_max_dose_given(
    doses: list[LocalAnaestheticDose], patient_weight: float
) -> float:
    return sum(
        [
            calculate_percentage_of_max_dose(
                LocalAnaestheticDose(*dose), patient_weight
            )
            for dose in doses
        ]
    )


def calculated_max_allowed_for_current_drug(
    doses: list[LocalAnaestheticDose],
    patient_weight: float,
    potential_dose: LocalAnaestheticDose,
) -> float:
    if not doses:
        return calculate_max_drug_dose(
            patient_weight, potential_dose.drug, float(potential_dose.concentration)
        )

    current_proportion = proportion_of_max_dose_given(doses, patient_weight)
    max_for_drug = calculate_max_drug_dose(
        patient_weight, potential_dose.drug, float(potential_dose.concentration)
    )
    return max_for_drug * (1 - current_proportion)


def check_if_dose_is_dangerous(
    doses: list[LocalAnaestheticDose],
    patient_weight: float,
    potential_dose: LocalAnaestheticDose,
) -> bool:
    return calculated_max_allowed_for_current_drug(
        doses, patient_weight, potential_dose
    ) < float(potential_dose.dose_in_ml)
