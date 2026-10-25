import type { Tour } from "../types";
import { adminTour } from "./admin";
import { billingTour } from "./billing";
import { doctorTour } from "./doctor";
import { emergencyTour } from "./emergency";
import { opsTour } from "./ops";
import { patientTour } from "./patient";
import { pharmacistTour } from "./pharmacist";
import { receptionistTour } from "./receptionist";

import { systemDesignTour } from "./systemDesign";

export const allTours: Tour[] = [patientTour, receptionistTour, doctorTour, pharmacistTour, billingTour, emergencyTour, adminTour, opsTour, systemDesignTour];
