"use client";

import { FormEvent, useState } from "react";
import { useLocation } from "@/hooks/useLocation";
import { ProductGroup, SearchError, searchProducts } from "@/lib/api";
import styles from "./page.module.css";

function formatQuantity(quantity: ProductGroup["normalized_quantity"]) {
  if (!quantity) return null;
  if (quantity.unit === "g" && quantity.amount >= 1000) {
    return `${(quantity.amount / 1000).toLocaleString("de-AT")} kg`;
  }
  if (quantity.unit === "ml" && quantity.amount >= 1000) {
    return `${(quantity.amount / 1000).toLocaleString("de-AT")} l`;
  }
  return `${quantity.amount.toLocaleString("de-AT")} ${quantity.unit}`;
}

function formatPrice(price: number) {
  return price.toLocaleString("de-AT", { style: "currency", currency: "EUR" });
}

export default function Home() {
  const { location, setManualZipCode } = useLocation();
  const [query, setQuery] = useState("");
  const [zipCodeInput, setZipCodeInput] = useState("");
  const [results, setResults] = useState<ProductGroup[] | null>(null);
  const [resolvedZipCode, setResolvedZipCode] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const needsManualZipCode = location.status === "unresolved";

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    if (!query.trim()) return;

    const searchLocation =
      location.status === "gps"
        ? { lat: location.lat, lon: location.lon }
        : location.status === "manual"
          ? { zipCode: location.zipCode }
          : null;

    if (!searchLocation) {
      setError("Bitte gib eine Postleitzahl an, damit wir Läden in deiner Nähe finden können.");
      return;
    }

    setLoading(true);
    try {
      const response = await searchProducts(query.trim(), searchLocation);
      setResults(response.results);
      setResolvedZipCode(response.zip_code);
    } catch (err) {
      setResults(null);
      setError(err instanceof SearchError ? err.message : "Etwas ist schiefgelaufen.");
    } finally {
      setLoading(false);
    }
  }

  function handleZipCodeSubmit(event: FormEvent) {
    event.preventDefault();
    if (zipCodeInput.trim()) {
      setManualZipCode(zipCodeInput.trim());
    }
  }

  return (
    <main className={styles.page}>
      <h1>Billiger</h1>
      <p className={styles.subtitle}>Wo ist dein Produkt gerade am günstigsten?</p>

      {location.status === "detecting" && <p>Standort wird ermittelt …</p>}

      {needsManualZipCode && (
        <form onSubmit={handleZipCodeSubmit} className={styles.form}>
          <label htmlFor="zip-code">
            Standort konnte nicht automatisch ermittelt werden. Postleitzahl eingeben:
          </label>
          <div className={styles.row}>
            <input
              id="zip-code"
              inputMode="numeric"
              pattern="[0-9]{4}"
              placeholder="1010"
              value={zipCodeInput}
              onChange={(e) => setZipCodeInput(e.target.value)}
            />
            <button type="submit">Übernehmen</button>
          </div>
        </form>
      )}

      {(location.status === "gps" || location.status === "manual") && (
        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.row}>
            <input
              type="text"
              placeholder="z.B. Nutella"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label="Produktsuche"
            />
            <button type="submit" disabled={loading}>
              {loading ? "Suche …" : "Suchen"}
            </button>
          </div>
        </form>
      )}

      {error && <p className={styles.error}>{error}</p>}

      {results && (
        <section className={styles.results}>
          {resolvedZipCode && (
            <p className={styles.subtitle}>Ergebnisse für PLZ {resolvedZipCode}</p>
          )}
          {results.length === 0 && <p>Keine Angebote gefunden.</p>}
          {results.map((group, i) => {
            const quantityLabel = formatQuantity(group.normalized_quantity);
            return (
            <article key={i} className={styles.resultCard}>
              <h2>
                {group.brand} {group.name}
                {quantityLabel && (
                  <span className={styles.quantity}> ({quantityLabel})</span>
                )}
              </h2>
              <p className={styles.cheapest}>
                Am günstigsten bei <strong>{group.cheapest.advertiser}</strong> für{" "}
                <strong>{formatPrice(group.cheapest.price)}</strong>
              </p>
              <ul className={styles.offerList}>
                {group.offers
                  .slice()
                  .sort((a, b) => a.price - b.price)
                  .map((offer, j) => (
                    <li key={j}>
                      {offer.advertiser}: {formatPrice(offer.price)}
                    </li>
                  ))}
              </ul>
            </article>
            );
          })}
        </section>
      )}
    </main>
  );
}
