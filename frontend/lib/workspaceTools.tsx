"use client";
import { createContext, useContext } from "react";

// Legacy boards can render inside the new shell without advertising removed tools.
export const WorkspaceToolsContext = createContext(true);
export const useWorkspaceTools = () => useContext(WorkspaceToolsContext);
