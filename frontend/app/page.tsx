"use client";

import { FormEvent, useState } from "react";
import { useAccount } from "@/hooks/useAccount";
import { useLocation } from "@/hooks/useLocation";
import { useShoppingList } from "@/hooks/useShoppingList";
import { useStreak } from "@/hooks/useStreak";
import {
  CartComparisonError,
  CartComparisonResponse,
  ProductGroup,
  SearchError,
  compareCart,
  searchProducts,
} from "@/lib/api";
import { AccountPanel } from "./AccountPanel";
import { AssistantWidget } from "./AssistantWidget";
import { CartComparisonView } from "./CartComparison";
import { HomeHero } from "./HomeHero";
import { ShoppingListView } from "./ShoppingList";
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

function resolveSearchLocation(location: ReturnType<typeof useLocation>["location"]) {
  if (location.status === "gps") return { lat: location.lat, lon: location.lon };
  if (location.status === "manual") return { zipCode: location.zipCode };
  return null;
}

export default function Home() {
  const { location, setManualZipCode } = useLocation();
  const shoppingList = useShoppingList();
  const { session } = useAccount();
  const streak = useStreak(session?.token ?? null);
  const [query, setQuery] = useState("");
  const [zipCodeInput, setZipCodeInput] = useState("");
  const [results, setResults] = useState<ProductGroup[] | null>(null);
  const [resolvedZipCode, setResolvedZipCode] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [comparison, setComparison] = useState<CartComparisonResponse | null>(null);
  const [comparisonError, setComparisonError] = useState<string | null>(null);
  const [comparing, setComparing] = useState(false);

  const needsManualZipCode = location.status === "unresolved";

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    if (!query.trim()) return;

    const searchLocation = resolveSearchLocation(location);

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

  async function handleCompare() {
    setComparisonError(null);

    const searchLocation = resolveSearchLocation(location);
    if (!searchLocation) {
      setComparisonError(
        "Bitte gib eine Postleitzahl an, damit wir Läden in deiner Nähe finden können."
      );
      return;
    }
    if (shoppingList.items.length === 0) return;

    setComparing(true);
    try {
      const response = await compareCart(
        shoppingList.items.map((item) => ({
          name: item.name,
          brand: item.brand,
          quantity: item.quantity,
        })),
        searchLocation,
        session?.token
      );
      setComparison(response);
      streak.refresh();
    } catch (err) {
      setComparison(null);
      setComparisonError(
        err instanceof CartComparisonError ? err.message : "Etwas ist schiefgelaufen."
      );
    } finally {
      setComparing(false);
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

      <AccountPanel />

      {streak.summary && <HomeHero summary={streak.summary} />}

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
              <button
                type="button"
                onClick={() =>
                  shoppingList.addItem({
                    name: group.name ?? group.brand ?? "Unbenanntes Produkt",
                    brand: group.brand,
                    category: group.categories[0] ?? null,
                  })
                }
              >
                Zur Liste hinzufügen
              </button>
            </article>
            );
          })}
        </section>
      )}

      <ShoppingListView list={shoppingList} />

      {shoppingList.items.length > 0 && (
        <section className={styles.results}>
          <button type="button" onClick={handleCompare} disabled={comparing}>
            {comparing ? "Vergleiche …" : "Warenkorb vergleichen"}
          </button>
          {comparisonError && <p className={styles.error}>{comparisonError}</p>}
          {comparison && <CartComparisonView result={comparison} />}
        </section>
      )}

      <AssistantWidget token={session?.token ?? null} location={resolveSearchLocation(location)} />
    </main>
  );
}
