import { createContext, useContext, useEffect, useMemo, useState } from 'react';

export type ExplainabilityLevel = 'summary' | 'inspect' | 'forensic';

interface ExplainabilityContextType {
  globalLevel: ExplainabilityLevel;
  setGlobalLevel: (level: ExplainabilityLevel) => void;
  getLevelFor: (scope: string) => ExplainabilityLevel;
  setLocalLevel: (scope: string, level: ExplainabilityLevel | null) => void;
}

const ExplainabilityContext = createContext<ExplainabilityContextType | undefined>(undefined);

const GLOBAL_KEY = 'tpa.explainability.global';
const LOCAL_KEY = 'tpa.explainability.local';

export function ExplainabilityProvider({ children }: { children: React.ReactNode }) {
  const [globalLevel, setGlobalLevelState] = useState<ExplainabilityLevel>('summary');
  const [localLevels, setLocalLevels] = useState<Record<string, ExplainabilityLevel>>({});

  useEffect(() => {
    const storedGlobal = window.localStorage.getItem(GLOBAL_KEY);
    if (storedGlobal === 'summary' || storedGlobal === 'inspect' || storedGlobal === 'forensic') {
      setGlobalLevelState(storedGlobal);
    }
    const storedLocal = window.localStorage.getItem(LOCAL_KEY);
    if (storedLocal) {
      try {
        const parsed = JSON.parse(storedLocal);
        if (parsed && typeof parsed === 'object') {
          setLocalLevels(parsed);
        }
      } catch (err) {
        console.warn('Failed to parse explainability local prefs', err);
      }
    }
  }, []);

  const setGlobalLevel = (level: ExplainabilityLevel) => {
    setGlobalLevelState(level);
    window.localStorage.setItem(GLOBAL_KEY, level);
  };

  const setLocalLevel = (scope: string, level: ExplainabilityLevel | null) => {
    setLocalLevels((prev) => {
      const next = { ...prev };
      if (level === null) {
        delete next[scope];
      } else {
        next[scope] = level;
      }
      window.localStorage.setItem(LOCAL_KEY, JSON.stringify(next));
      return next;
    });
  };

  const getLevelFor = (scope: string) => {
    return localLevels[scope] || globalLevel;
  };

  const value = useMemo(
    () => ({ globalLevel, setGlobalLevel, getLevelFor, setLocalLevel }),
    [globalLevel, localLevels]
  );

  return <ExplainabilityContext.Provider value={value}>{children}</ExplainabilityContext.Provider>;
}

export function useExplainability(scope?: string) {
  const context = useContext(ExplainabilityContext);
  if (!context) {
    throw new Error('useExplainability must be used within ExplainabilityProvider');
  }
  const level = scope ? context.getLevelFor(scope) : context.globalLevel;
  return {
    level,
    globalLevel: context.globalLevel,
    setGlobalLevel: context.setGlobalLevel,
    setLocalLevel: context.setLocalLevel,
  };
}
