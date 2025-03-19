import uvicorn
from api.calc_types import Drug, DrugDose, LocalAnaestheticDrug, Patient
from fastapi import FastAPI

app = FastAPI()


@app.get("/drugs")
async def get_available_drugs() -> list[Drug]:
    """List drugs available in calculator"""
    return [drug.value for drug in LocalAnaestheticDrug]


@app.get("/patient/create")
async def get_patient(weight: float) -> Patient:
    """Create patient from weight"""
    return Patient(weight=weight, doses=[])


@app.post("/patient/add_dose")
async def add_dose(patient: Patient, dose: DrugDose) -> Patient:
    """Add dose to patient"""
    patient.add_dose(dose)
    return patient


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9090)
