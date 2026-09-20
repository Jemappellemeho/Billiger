"use client";

import { describeStreak, StreakSummary } from "@/lib/streak";
import styles from "./HomeHero.module.css";

const DETAIL_ROWS = 3;

function formatPrice(price: number) {
  return price.toLocaleString("de-AT", { style: "currency", currency: "EUR" });
}

function flameClass(lit: boolean, dimmed: boolean) {
  if (!lit) return styles.unlit;
  return dimmed ? styles.dim : styles.lit;
}

/**
 * Home hero for signed-in accounts: this week's savings and the streak, visible
 * without any interaction. The "Details" disclosure adds the second reference
 * price and which stores/products the savings came from.
 */
export function HomeHero({ summary }: { summary: StreakSummary }) {
  const display = describeStreak(summary.streak);
  const week = summary.this_week;
  const topItem = week?.items[0];

  return (
    <section className={styles.hero} aria-label="Ersparnis und Streak">
      {week ? (
        <>
          <p className={styles.caption}>Gespart diese Woche</p>
          <p className={styles.amount}>{formatPrice(week.savings_vs_most_expensive)}</p>
          <p className={styles.reference}>im Vergleich zum teuersten Laden</p>
        </>
      ) : (
        <>
          <p className={styles.caption}>Diese Woche</p>
          <p className={`${styles.amount} ${styles.empty}`}>–</p>
          <p className={styles.reference}>Noch kein Vergleich abgeschlossen</p>
        </>
      )}

      <div className={styles.streak}>
        <span className={styles.flames} aria-hidden="true">
          {Array.from({ length: display.totalFlames }, (_, i) => (
            <span key={i} className={flameClass(i < display.litFlames, display.dimmed)}>
              🔥
            </span>
          ))}
        </span>
        <span className={styles.streakLabel}>Streak: {display.label}</span>
      </div>
      <p className={styles.note}>{display.note}</p>

      {topItem && (
        <p className={styles.top}>
          Größter Anteil: {topItem.name} bei {topItem.advertiser}
          {topItem.on_sale ? " (Angebot)" : ""}
        </p>
      )}

      <details className={styles.details}>
        <summary>Details</summary>
        {week && (
          <dl>
            <div>
              <dt>ggü. teuerstem Laden</dt>
              <dd>{formatPrice(week.savings_vs_most_expensive)}</dd>
            </div>
            <div>
              <dt>ggü. regulärem Preis</dt>
              <dd>{formatPrice(week.savings_vs_regular)}</dd>
            </div>
          </dl>
        )}
        {week && week.items.length > 0 && (
          <>
            <h3>Größte Einzelposten</h3>
            <ul>
              {week.items.slice(0, DETAIL_ROWS).map((item, i) => (
                <li key={i}>
                  <span>
                    {item.name} · {item.advertiser}
                    {item.on_sale ? " (Angebot)" : ""}
                  </span>
                  <span>−{formatPrice(item.savings_vs_most_expensive)}</span>
                </li>
              ))}
            </ul>
          </>
        )}
        {week && week.stores.length > 0 && (
          <>
            <h3>Läden mit dem größten Anteil</h3>
            <ul>
              {week.stores.slice(0, DETAIL_ROWS).map((store) => (
                <li key={store.advertiser}>
                  <span>{store.advertiser}</span>
                  <span>−{formatPrice(store.savings_vs_most_expensive)}</span>
                </li>
              ))}
            </ul>
          </>
        )}
        <p className={styles.total}>
          Insgesamt gespart: {formatPrice(summary.total_savings.vs_most_expensive)} (ggü. teuerstem
          Laden) · {formatPrice(summary.total_savings.vs_regular)} (ggü. regulärem Preis)
        </p>
      </details>
    </section>
  );
}
