import { useEffect, useState } from "react";

const CHANGE_EVENT = "carewise-preference-change";

function read(key: string, defaultOn: boolean): boolean {
  try {
    const value = localStorage.getItem(key);
    return value === null ? defaultOn : value === "on";
  } catch {
    return defaultOn;
  }
}

/**
 * An on/off preference remembered in this browser only (never sent to the server). Every component
 * using the same key stays in sync. If storage is blocked (private mode), it still works for the visit.
 */
export function usePreference(key: string, defaultOn: boolean): [boolean, (on: boolean) => void] {
  const [on, setOn] = useState(() => read(key, defaultOn));
  useEffect(() => {
    const sync = (e: Event) => {
      if ((e as CustomEvent<string>).detail === key) setOn(read(key, defaultOn));
    };
    window.addEventListener(CHANGE_EVENT, sync);
    return () => window.removeEventListener(CHANGE_EVENT, sync);
  }, [key, defaultOn]);
  const set = (value: boolean) => {
    try {
      localStorage.setItem(key, value ? "on" : "off");
    } catch {
      // Blocked storage: change it for this visit only.
    }
    setOn(value);
    window.dispatchEvent(new CustomEvent(CHANGE_EVENT, { detail: key }));
  };
  return [on, set];
}
