import React, { createContext, useContext, useState, useEffect, useMemo, useCallback } from "react";
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
import { AlertCircle, RefreshCw, Trash2, Moon, Sun } from "lucide-react";

// Theme context
const ThemeContext = createContext({
  theme: 'light',
  toggleTheme: () => {},
});

// Theme provider component
const ThemeProvider = ({ children }) => {
  const [theme, setTheme] = useState('light');

  const toggleTheme = useCallback(() => {
    setTheme((prevTheme) => (prevTheme === 'light' ? 'dark' : 'light'));
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark');
  }, [theme]);

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
};


const LocalAnaestheticDrug = {
  LIDOCAINE: { name: "Lidocaine", maxDose: 4.5, concentrations: [0.5, 1] },
  BUPIVACAINE: {
    name: "Bupivacaine",
    maxDose: 2.0,
    concentrations: [0.25, 0.5],
  },
  ROPIVACAINE: {
    name: "Ropivacaine",
    maxDose: 3.0,
    concentrations: [0.2, 0.75],
  },
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
  const { theme, toggleTheme } = useContext(ThemeContext);
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

  const unsafeDosesCount = useMemo(() => {
    return cumulativeSafety.filter((safe) => !safe).length;
  }, [cumulativeSafety]);

  const canAddDose = useMemo(() => {
    return unsafeDosesCount === 0;
  }, [unsafeDosesCount]);

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

  const handleDeleteDose = (index: number) => {
    const updatedDoses = patient.doses.filter((_, i) => i !== index);
    setPatient({ ...patient, doses: updatedDoses });
  };

  // const DosesAdministered = ({ patient, handleDeleteDose, isDoseSafe, cumulativeSafety }) => {
  //   const containerRef = useRef(null);
  //   const headerRef = useRef(null);
  //   const [contentHeight, setContentHeight] = useState('auto');

  //   useEffect(() => {
  //     const updateHeight = () => {
  //       if (containerRef.current && headerRef.current) {
  //         const containerHeight = containerRef.current.clientHeight;
  //         const headerHeight = headerRef.current.clientHeight;
  //         const newContentHeight = containerHeight - headerHeight;
  //         setContentHeight(`${newContentHeight}px`);
  //       }
  //     };

  //     updateHeight();
  //     window.addEventListener('resize', updateHeight);

  //     return () => window.removeEventListener('resize', updateHeight);
  //   }, []);

  return (
    <div className="container mx-auto p-4">
      <Card className="mb-4">
        <CardHeader>
          <CardTitle className="flex justify-between items-center flex-wrap gap-2">
            <span className="text-lg sm:text-xl">
              Local Anaesthetic Dose Calculator
            </span>
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
                <Select
                  value={newDose.concentration.toString()}
                  onValueChange={(value) =>
                    setNewDose({
                      ...newDose,
                      concentration: parseFloat(value),
                    })}
                  disabled={!newDose.drugName}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Select concentration" />
                  </SelectTrigger>
                  <SelectContent>
                    {newDose.drugName &&
                      LocalAnaestheticDrug[
                        newDose.drugName as keyof typeof LocalAnaestheticDrug
                      ].concentrations.map((conc) => (
                        <SelectItem key={conc} value={conc.toString()}>
                          {conc}%
                        </SelectItem>
                      ))}
                  </SelectContent>
                </Select>
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
                <Button
                  onClick={handleAddDose}
                  className="w-full"
                  disabled={!canAddDose}
                >
                  Add Dose
                </Button>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
      <Card className="flex flex-col">
        <CardHeader className="flex-shrink-0">
          <CardTitle>Doses Administered</CardTitle>
        </CardHeader>
        <CardContent className="flex-grow overflow-y-auto">
          {patient.doses.length === 0
            ? <p>No doses administered yet.</p>
            : (
              <div className="h-full overflow-y-auto">
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
                          {LocalAnaestheticDrug[
                            dose.drugName as keyof typeof LocalAnaestheticDrug
                          ].name} {dose.concentration}% {dose.doseInMl}ml
                          {!isSafe && (
                            <span className="ml-2 text-red-600">(Unsafe)</span>
                          )}
                        </span>
                        <div className="flex items-center">
                          {!isSafe && (
                            <AlertCircle className="text-red-500 mr-2" />
                          )}
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleDeleteDose(index)}
                            className="p-1"
                          >
                            <Trash2 className="h-4 w-4 text-red-500" />
                          </Button>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}
          {patient.doses.length > 0 && (
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
          )}
        </CardContent>
      </Card>
    </div>
  );
}
