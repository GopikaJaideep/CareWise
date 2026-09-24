import { useEffect } from "react";

/** Sets the browser tab title for the current page, so tabs, history and screen readers say where you are. */
export function usePageTitle(title: string) {
  useEffect(() => {
    document.title = title ? `${title} · CareWise` : "CareWise: support for cancer caregivers";
  }, [title]);
}
