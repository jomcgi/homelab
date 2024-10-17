import React, { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AlertCircle, RefreshCw } from "lucide-react";

const LocalAnaestheticDrug = {
  LIDOCAINE: { name: "Lidocaine", maxDose: 3.0 },
  BUPIVACAINE: { name: "Bupivacaine", maxDose: 2.0 },
};

interface DrugDose {
  drugName: string;
  concentration: number;
  doseInMl: number;
}

interface Patient {
  weight: number;
  doses: DrugDose[];
}

const initialPatient: Patient = { weight: 0, doses: [] };
const initialDose: DrugDose = { drugName: "", concentration: 0, doseInMl: 0 };

export default function DoseCalculator() {
  const [patient, setPatient] = useState<Patient>(initialPatient);
  const [newDose, setNewDose] = useState<DrugDose>(initialDose);

  const calculateMaxDoseInMl = (dose: DrugDose, weight: number): number => {
    const drug =
      LocalAnaestheticDrug[dose.drugName as keyof typeof LocalAnaestheticDrug];
    const maxInMg = drug.maxDose * weight;
    return (maxInMg / 10) * (1 / dose.concentration);
  };

  const calculatePortionOfMaxDose = (
    dose: DrugDose,
    weight: number,
  ): number => {
    return dose.doseInMl / calculateMaxDoseInMl(dose, weight);
  };

  const isDoseSafe = (doses: DrugDose[], weight: number): boolean => {
    const totalPortion = doses.reduce(
      (sum, dose) => sum + calculatePortionOfMaxDose(dose, weight),
      0,
    );
    return totalPortion <= 1;
  };

  const cumulativeSafety = useMemo(() => {
    let cumulativePortion = 0;
    return patient.doses.map((dose) => {
      cumulativePortion += calculatePortionOfMaxDose(dose, patient.weight);
      return cumulativePortion <= 1;
    });
  }, [patient.doses, patient.weight]);

  const handleAddDose = () => {
    if (!patient.weight) {
      alert("Please enter patient weight before adding a dose.");
      return;
    }
    if (patient.weight <= 40) {
      alert("Patient weight must be greater than 40kg.");
    }
    if (newDose.drugName && newDose.concentration > 0 && newDose.doseInMl > 0) {
      const updatedDoses = [...patient.doses, newDose];
      setPatient({ ...patient, doses: updatedDoses });
    } else {
      alert("Please fill in all dose details before adding.");
    }
  };

  const handleReset = () => {
    setPatient(initialPatient);
    setNewDose(initialDose);
  };



  return (
    <div className="container mx-auto p-4">
      <Card className="mb-4">
        <CardHeader>
          <CardTitle className="flex justify-between items-center flex-wrap gap-2">
            <span className="text-lg sm:text-xl">Local Anaesthetic Dose Calculator</span>
            <Button variant="outline" size="sm" onClick={handleReset}>
              <RefreshCw className="mr-2 h-4 w-4" /> Reset
            </Button>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div>
              <label
                htmlFor="weight"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                Patient Weight (kg)
              </label>
              <Input
                id="weight"
                type="number"
                value={patient.weight || ""}
                onChange={(e) =>
                  setPatient({
                    ...patient,
                    weight: parseFloat(e.target.value) || 0,
                  })}
                className="w-full"
                placeholder="Enter patient weight"
              />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div>
                <label
                  htmlFor="drug"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
                  Drug
                </label>
                <Select
                  value={newDose.drugName}
                  onValueChange={(value) =>
                    setNewDose({ ...newDose, drugName: value })}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Select a drug" />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(LocalAnaestheticDrug).map(([key, drug]) => (
                      <SelectItem key={key} value={key}>
                        {drug.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label
                  htmlFor="concentration"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
                  Concentration (%)
                </label>
                <Input
                  id="concentration"
                  type="number"
                  value={newDose.concentration || ""}
                  onChange={(e) =>
                    setNewDose({
                      ...newDose,
                      concentration: parseFloat(e.target.value) || 0,
                    })}
                  className="w-full"
                  placeholder="Enter concentration"
                />
              </div>
              <div>
                <label
                  htmlFor="dose"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
                  Dose (ml)
                </label>
                <Input
                  id="dose"
                  type="number"
                  value={newDose.doseInMl || ""}
                  onChange={(e) =>
                    setNewDose({
                      ...newDose,
                      doseInMl: parseFloat(e.target.value) || 0,
                    })}
                  className="w-full"
                  placeholder="Enter dose"
                />
              </div>
              <div className="flex items-end">
                <Button onClick={handleAddDose} className="w-full">
                  Add Dose
                </Button>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    <Card className="h-[55vh] flex flex-col">
      <CardHeader>
        <CardTitle>Doses Administered</CardTitle>
      </CardHeader>
      <CardContent className="flex-grow overflow-hidden">
        {patient.doses.length === 0 ? (
          <p>No doses administered yet.</p>
        ) : (
          <div className="h-full overflow-y-auto pr-2">
            <ul className="space-y-2">
              {patient.doses.map((dose, index) => {
                const isSafe = cumulativeSafety[index];
                return (
                  <li
                    key={index}
                    className={`flex items-center justify-between p-2 rounded ${
                      isSafe ? "bg-green-100" : "bg-red-100"
                    }`}
                  >
                    <span>
                      {LocalAnaestheticDrug[dose.drugName].name} {dose.concentration}% {dose.doseInMl}ml
                      {!isSafe && (
                        <span className="ml-2 text-red-600">(Unsafe)</span>
                      )}
                    </span>
                    {!isSafe && <AlertCircle className="text-red-500" />}
                  </li>
                );
              })}
            </ul>
          </div>
        )}
        <div className="mt-4">
          <p
            className={`font-bold ${
              isDoseSafe(patient.doses, patient.weight)
                ? "text-green-600"
                : "text-red-600"
            }`}
          >
            {isDoseSafe(patient.doses, patient.weight)
              ? "Safe Total Dose"
              : "Unsafe Total Dose"}
          </p>
        </div>
      </CardContent>
    </Card>
    </div>
  );
}
