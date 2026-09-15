"use client";

import { useMemo, useState } from "react";
import { CartComparisonResponse, CartLine } from "@/lib/api";
import styles from "./CartComparison.module.css";

function formatPrice(price: number) {
  return price.toLocaleString("de-AT", { style: "currency", currency: "EUR" });
}

/**
 * Non-binding soft hint only — never a ✅/⚠️ verdict. The user decides
 * whether an extra stop is worth it; this just adds a bit of color to the
 * number, scaled relative to the single-store baseline so "deutlich"/"wenig"
 * means something across very different shopping list sizes.
 */
function softHint(marginalSavings: number, singleStoreTotal: number) {
  if (marginalSavings <= 0 || singleStoreTotal <= 0) return null;
  return marginalSavings / singleStoreTotal >= 0.03 ? "spart noch deutlich" : "spart nur noch wenig";
}

function groupByStore(lines: CartLine[]) {
  const groups = new Map<string, CartLine[]>();
  for (const line of lines) {
    groups.set(line.advertiser, [...(groups.get(line.advertiser) ?? []), line]);
  }
  return groups;
}

export function CartComparisonView({ result }: { result: CartComparisonResponse }) {
  const { ladder } = result;
  const maxStops = ladder.length;
  const [stops, setStops] = useState(1);

  // Reset to the single-store baseline whenever a fresh comparison comes in,
  // so a stale slider position from a previous (differently-sized) list
  // can't outlive the ladder it was set against. Adjusted during render
  // (React's recommended pattern for this) rather than in an effect, which
  // would cause an extra cascading render.
  const [prevResult, setPrevResult] = useState(result);
  if (result !== prevResult) {
    setPrevResult(result);
    setStops(1);
  }

  const currentRung = useMemo(() => ladder[Math.min(Math.max(stops, 1), maxStops) - 1], [ladder, stops, maxStops]);

  if (maxStops === 0 || !currentRung) {
    return (
      <section className={styles.section}>
        <h2>Warenkorb-Vergleich</h2>
        <p className={styles.empty}>Für deine Liste gibt es aktuell keine Vergleichsdaten.</p>
        {result.unavailable_items.length > 0 && (
          <p className={styles.unavailable}>Nicht gefunden: {result.unavailable_items.join(", ")}</p>
        )}
      </section>
    );
  }

  const isSingle = stops <= 1;
  const isFull = stops >= maxStops;
  const assignmentByStore = groupByStore(currentRung.assignment);

  return (
    <section className={styles.section}>
      <h2>Warenkorb-Vergleich</h2>

      <div className={styles.toggle}>
        <button
          type="button"
          className={isSingle ? styles.toggleActive : undefined}
          onClick={() => setStops(1)}
        >
          1 Laden
        </button>
        <button
          type="button"
          className={isFull ? styles.toggleActive : undefined}
          onClick={() => setStops(maxStops)}
        >
          Voll aufgeteilt ({maxStops} {maxStops === 1 ? "Laden" : "Läden"})
        </button>
      </div>

      <div className={styles.heroTotal}>{formatPrice(currentRung.total)}</div>

      {result.unavailable_items.length > 0 && (
        <p className={styles.unavailable}>Nicht gefunden: {result.unavailable_items.join(", ")}</p>
      )}

      <div className={styles.sliderRow}>
        <span className={styles.muted}>1 Stopp</span>
        <input
          type="range"
          min={1}
          max={maxStops}
          value={stops}
          aria-label="Anzahl Stopps"
          onChange={(e) => setStops(Number(e.target.value))}
        />
        <span className={styles.muted}>{maxStops} Stopps</span>
      </div>

      <div className={styles.stopCards}>
        {currentRung.stores.map((advertiser) => {
          const items = assignmentByStore.get(advertiser) ?? [];
          const storeTotal = items.reduce((sum, line) => sum + line.price, 0);
          return (
            <div key={advertiser} className={styles.stopCard}>
              <div className={styles.row}>
                <strong>{advertiser}</strong>
                <span>{formatPrice(storeTotal)}</span>
              </div>
              <div className={styles.stopItems}>{items.map((line) => line.name).join(", ")}</div>
            </div>
          );
        })}
      </div>

      <h3 className={styles.ladderHeading}>Stufen-Leiter</h3>
      <ul className={styles.ladderList}>
        {ladder.map((rung) => {
          const hint = rung.stops === 1 ? null : softHint(rung.marginal_savings, ladder[0].total);
          return (
            <li key={rung.stops}>
              <button
                type="button"
                className={rung.stops === stops ? styles.ladderRowActive : styles.ladderRow}
                onClick={() => setStops(rung.stops)}
              >
                <span className={styles.ladderBadge}>{rung.stops}</span>
                <span className={styles.ladderInfo}>
                  <span>{rung.stores.join(" + ")}</span>
                  <span className={styles.ladderMarginal}>
                    {rung.stops === 1
                      ? "Ein Laden für die ganze Liste"
                      : `+${formatPrice(rung.marginal_savings)} zusätzlich gespart${
                          hint ? ` — ${hint}` : ""
                        }`}
                  </span>
                </span>
                <span className={styles.ladderTotal}>{formatPrice(rung.total)}</span>
              </button>
            </li>
          );
        })}
      </ul>

      <div className={styles.itemSavings}>
        <h3>Ersparnis je Produkt</h3>
        <ul className={styles.itemSavingsList}>
          {currentRung.assignment.map((line) => (
            <li key={`${line.brand ?? ""}|${line.name}`} className={styles.itemSavingsRow}>
              <span>
                {line.brand ? `${line.brand} ` : ""}
                {line.name} · {line.advertiser}
              </span>
              <span className={styles.muted}>
                {formatPrice(line.price)} · ggü. teuerstem {formatPrice(line.savings_vs_most_expensive)}
                {line.savings_vs_regular !== null && (
                  <> · ggü. regulär {formatPrice(line.savings_vs_regular)}</>
                )}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
