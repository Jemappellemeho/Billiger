import { describe, expect, test } from "vitest";
import { describeStreak, StreakSummary } from "./streak";

function summary(overrides: Partial<StreakSummary["streak"]> = {}, thisWeek = true): StreakSummary {
  return {
    current_week: "2026-09-21",
    streak: {
      weeks: 3,
      status: "active",
      missed_weeks: 0,
      last_completed_week: "2026-09-21",
      ...overrides,
    },
    this_week: thisWeek
      ? {
          savings_vs_most_expensive: 14.8,
          savings_vs_regular: 8.2,
          stores: [{ advertiser: "LIDL", savings_vs_most_expensive: 9 }],
          items: [
            {
              name: "Red Bull",
              brand: null,
              advertiser: "LIDL",
              savings_vs_most_expensive: 9,
              savings_vs_regular: 8.2,
              on_sale: true,
            },
          ],
        }
      : null,
    total_savings: { vs_most_expensive: 40, vs_regular: 20 },
    history: [],
  };
}

describe("describeStreak", () => {
  test("an active streak lights one flame per week and confirms this week is done", () => {
    const display = describeStreak(summary({ weeks: 3, status: "active" }).streak);

    expect(display.label).toBe("3 Wochen");
    expect(display.litFlames).toBe(3);
    expect(display.dimmed).toBe(false);
    expect(display.note).toMatch(/erledigt/);
  });

  test("a single week is singular", () => {
    expect(describeStreak(summary({ weeks: 1 }).streak).label).toBe("1 Woche");
  });

  test("the flame row is capped so a long streak stays compact", () => {
    const display = describeStreak(summary({ weeks: 12 }).streak);

    expect(display.litFlames).toBe(display.totalFlames);
  });

  test("a streak whose week is still open stays lit and invites a comparison", () => {
    const display = describeStreak(summary({ weeks: 2, status: "pending" }).streak);

    expect(display.dimmed).toBe(false);
    expect(display.litFlames).toBe(2);
    expect(display.note).toMatch(/noch offen/);
  });

  test("a paused streak keeps its value, dims the flames and stays free of blame", () => {
    const display = describeStreak(summary({ weeks: 3, status: "paused", missed_weeks: 2 }).streak);

    expect(display.label).toBe("3 Wochen");
    expect(display.litFlames).toBe(3);
    expect(display.dimmed).toBe(true);
    expect(display.note).toMatch(/pausiert/);
    expect(display.note).toMatch(/weiter/);
    expect(display.note).not.toMatch(/verpasst|verloren|unterbrochen|zurückgesetzt|leider/i);
  });

  test("no streak yet invites the first comparison", () => {
    const display = describeStreak(summary({ weeks: 0, status: "none" }).streak);

    expect(display.litFlames).toBe(0);
    expect(display.dimmed).toBe(false);
    expect(display.note).toMatch(/ersten Vergleich/);
  });
});
