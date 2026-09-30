import { createContext, useContext } from "react";

export const CaseContext = createContext(null);
export const useCase = () => useContext(CaseContext);
