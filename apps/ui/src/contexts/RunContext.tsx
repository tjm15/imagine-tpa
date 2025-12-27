import { createContext, useContext, useMemo, useState } from 'react';

interface RunContextType {
  currentRunId: string | null;
  currentRunStatus: string | null;
  setCurrentRun: (runId: string | null, status?: string | null) => void;
}

const RunContext = createContext<RunContextType | undefined>(undefined);

export function RunProvider({ children }: { children: React.ReactNode }) {
  const [currentRunId, setCurrentRunId] = useState<string | null>(null);
  const [currentRunStatus, setCurrentRunStatus] = useState<string | null>(null);

  const setCurrentRun = (runId: string | null, status?: string | null) => {
    setCurrentRunId(runId);
    if (typeof status !== 'undefined') {
      setCurrentRunStatus(status);
    }
  };

  const value = useMemo(
    () => ({ currentRunId, currentRunStatus, setCurrentRun }),
    [currentRunId, currentRunStatus]
  );

  return <RunContext.Provider value={value}>{children}</RunContext.Provider>;
}

export function useRun() {
  const context = useContext(RunContext);
  if (!context) {
    throw new Error('useRun must be used within RunProvider');
  }
  return context;
}
