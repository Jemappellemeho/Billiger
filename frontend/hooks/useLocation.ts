"use client";

import { useCallback, useEffect, useState } from "react";

export type LocationState =
  | { status: "detecting" }
  | { status: "gps"; lat: number; lon: number }
  | { status: "manual"; zipCode: string }
  | { status: "unresolved" };

/**
 * GPS is the default source; if geolocation is unavailable, the user denies
 * permission, or it times out, the caller falls back to a manual PLZ input
 * via setManualZipCode (map decision: "GPS automatisch, PLZ als Fallback").
 */
function geolocationAvailable() {
  return typeof navigator !== "undefined" && "geolocation" in navigator;
}

export function useLocation() {
  const [location, setLocation] = useState<LocationState>(() =>
    geolocationAvailable() ? { status: "detecting" } : { status: "unresolved" }
  );

  useEffect(() => {
    if (location.status !== "detecting") return;
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLocation({
          status: "gps",
          lat: position.coords.latitude,
          lon: position.coords.longitude,
        });
      },
      () => {
        setLocation({ status: "unresolved" });
      },
      { timeout: 10000 }
    );
  }, [location.status]);

  const setManualZipCode = useCallback((zipCode: string) => {
    setLocation({ status: "manual", zipCode });
  }, []);

  return { location, setManualZipCode };
}
