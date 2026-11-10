import { createContext, useContext, type ReactNode } from "react";

export const LibrarySessionContext = createContext<{sessionId: string; catalogingEnabled: boolean; folderImportEnabled?:boolean; fileMenu: ReactNode} | null>(null);
export const useLibrarySession = () => useContext(LibrarySessionContext);
