from typing import NamedTuple
import mesop as me
from calc_types import LocalAnaestheticDose, LocalAnaestheticDrug
from dataclasses import field
import pandas as pd

from calculator import (
    calculated_max_allowed_for_current_drug,
    check_if_dose_is_dangerous,
)


print("starting server")

@me.stateclass
class InputState:
    weight: float | None = None
    drug: str | None = None
    concentration: str | None = None
    dose_in_ml: str | None = None
    doses: list[LocalAnaestheticDose]

    def __post_init__(self):
        self.doses = []


def on_click_add_dose(e: me.ClickEvent):
    input_state = me.state(InputState)

    if (
        input_state.drug
        and input_state.concentration is not None
        and input_state.dose_in_ml is not None
    ):
        print(
            f"Adding dose: {input_state.drug}, {input_state.concentration}, {input_state.dose_in_ml}"
        )
        new_dose = LocalAnaestheticDose(
            drug=input_state.drug,
            concentration=input_state.concentration,
            dose_in_ml=input_state.dose_in_ml,
        )
        input_state.doses = input_state.doses + [new_dose]
    else:
        print("Error: Missing required fields for dose calculation")


@me.page(
    path="/",
    security_policy=me.SecurityPolicy(dangerously_disable_trusted_types=True),
)
def calculator():
    me.html(
        html="""
<link rel="preconnect" href="https://rsms.me/">
<link rel="stylesheet" href="https://rsms.me/inter/inter.css">
"""
    )
    input_state = me.state(InputState)
    with me.box(
        style=me.Style(
            margin=me.Margin(
                top=10,
                left=25,
                right=25,
                bottom=10,
            ),
        )
    ):
        me.text(
            text="Local Anaesthetic Calculator",
            type="headline-3",
            style=me.Style(
                font_family="Inter, sans-serif",
            ),
        )
        with me.box():
            me.text(
                text="Patient Weight:",
                type="body-1",
                style=me.Style(
                    font_family="Inter, sans-serif",
                ),
            )
            me.input(
                label="Patient Weight (kg)",
                appearance="outline",
                on_input=lambda e: setattr(input_state, "weight", float(e.value)),
                style=me.Style(width=500, font_family="Inter, sans-serif"),
            )

            me.text(
                text="Drug:",
                type="body-1",
                style=me.Style(
                    font_family="Inter, sans-serif",
                ),
            )
            me.select(
                label="Select drug",
                options=[
                    me.SelectOption(
                        label=drug.name,
                        value=drug.name,
                    )
                    for drug in LocalAnaestheticDrug
                ],
                style=me.Style(width=500, font_family="Inter, sans-serif"),
                on_selection_change=lambda e: setattr(input_state, "drug", e.value),
            )
            if input_state.drug:
                me.text(
                    text="Concentration:",
                    type="body-1",
                    style=me.Style(
                        font_family="Inter, sans-serif",
                    ),
                )
                me.select(
                    label="Select concentration",
                    options=[
                        me.SelectOption(
                            label=str(concentration.value),
                            value=str(concentration.value),
                        )
                        for concentration in LocalAnaestheticDrug[
                            input_state.drug
                        ].value.concentrations
                    ],
                    style=me.Style(width=500, font_family="Inter, sans-serif"),
                    on_selection_change=lambda e: setattr(
                        input_state, "concentration", str(e.value)
                    ),
                )
                with me.box(
                    style=me.Style(
                        display="flex",
                        gap=50,
                        grid_auto_columns="1fr",
                    )
                ):

                    with me.box():
                        me.text(
                            text="Dose in ml:",
                            type="body-1",
                            style=me.Style(
                                font_family="Inter, sans-serif",
                            ),
                        )
                        me.input(
                            label="Dose in ml",
                            appearance="outline",
                            on_input=lambda e: setattr(
                                input_state, "dose_in_ml", e.value
                            ),
                            style=me.Style(width=500, font_family="Inter, sans-serif"),
                        )
                    with me.box():
                        if input_state.drug and input_state.concentration:
                            me.text(
                                text="Max Dose Remaining:",
                                type="body-1",
                                style=me.Style(
                                    font_family="Inter, sans-serif",
                                ),
                            )
                            me.text(
                                text=f"{calculated_max_allowed_for_current_drug(input_state.doses, input_state.weight, LocalAnaestheticDose(drug=input_state.drug, concentration=input_state.concentration, dose_in_ml=input_state.dose_in_ml)):.2f}ml",
                                # larger text
                                type="headline-6",
                                style=me.Style(
                                    color="red",
                                    box_shadow="0 0 5px 0 rgba(0,0,0,0.2)",
                                    font_family="Inter, sans-serif",
                                ),
                            )

        with me.box(
            style=me.Style(
                display="flex",
                gap=20,
                grid_auto_columns="1fr",
                margin=me.Margin(
                    top=20,
                    bottom=20,
                ),
            )
        ):
            me.button(
                label="Add dose",
                on_click=on_click_add_dose,
                disabled=check_input_dose_invalid(
                    input_state.doses,
                    LocalAnaestheticDose(
                        drug=input_state.drug,
                        concentration=input_state.concentration,
                        dose_in_ml=input_state.dose_in_ml,
                    ),
                    input_state.weight,
                ),
                style=me.Style(
                    background="white",
                    box_shadow="0 0 5px 0 rgba(0,0,0,0.2)",
                    font_family="Inter, sans-serif",
                ),
            )
            me.button(
                label="Clear doses",
                on_click=lambda e: setattr(input_state, "doses", []),
                style=me.Style(
                    background="white",
                    box_shadow="0 0 5px 0 rgba(0,0,0,0.2)",
                    font_family="Inter, sans-serif",
                ),
            )
        me.text(
            text="Doses given:",
            type="body-1",
            style=me.Style(
                font_family="Inter, sans-serif",
            ),
        )
        with me.box(style=me.Style(display="flex", gap=50)):

            df = pd.DataFrame(
                input_state.doses,
                columns=LocalAnaestheticDose._fields,
            )
            df["DELETE"] = "X"
            with me.box(
                style=me.Style(
                    box_shadow="0 0 5px 0 rgba(0,0,0,0.2)",
                    cursor="pointer",
                    font_family="Inter, sans-serif",
                )
            ):
                me.table(
                    data_frame=df,
                    on_click=table_on_click,
                )


def check_input_dose_invalid(
    doses: list[LocalAnaestheticDose],
    potential_dose: LocalAnaestheticDose,
    patient_weight: float,
):
    if patient_weight is None:
        return True
    if potential_dose.dose_in_ml is None:
        return True
    if float(potential_dose.dose_in_ml) < 0:
        return True
    if potential_dose.concentration is None:
        return True
    if potential_dose.drug is None:
        return True
    if check_if_dose_is_dangerous(
        doses,
        patient_weight,
        potential_dose,
    ):
        return True
    return False


def table_on_click(e: me.TableClickEvent):
    print(f"Table clicked: {e}")
    input_state = me.state(InputState)
    if e.col_index == 3:
        input_state.doses = (
            input_state.doses[: e.row_index] + input_state.doses[e.row_index + 1 :]
        )
