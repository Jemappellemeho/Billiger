/** Wire format of GET /api/streak/ (see backend/streaks/tracking.py). */
export type StreakStatus = "none" | "active" | "pending" | "paused";

export type SavedItem = {
  name: string;
  brand: string | null;
  advertiser: string;
  savings_vs_most_expensive: number;
  savings_vs_regular: number;
  on_sale: boolean;
};

export type SavedStore = { advertiser: string; savings_vs_most_expensive: number };

export type WeekDetail = {
  savings_vs_most_expensive: number;
  savings_vs_regular: number;
  stores: SavedStore[];
  items: SavedItem[];
};

export type StreakSummary = {
  current_week: string;
  streak: {
    weeks: number;
    status: StreakStatus;
    missed_weeks: number;
    last_completed_week: string | null;
  };
  this_week: WeekDetail | null;
  total_savings: { vs_most_expensive: number; vs_regular: number };
  history: (WeekDetail & { week_start: string; completed: boolean })[];
};

const TOTAL_FLAMES = 5;

export type StreakDisplay = {
  label: string;
  note: string;
  litFlames: number;
  totalFlames: number;
  dimmed: boolean;
};

/**
 * How the streak is worded and drawn. A paused streak keeps its value and
 * only dims; the copy never says the streak was lost or a week was missed.
 */
export function describeStreak(streak: StreakSummary["streak"]): StreakDisplay {
  const base = {
    label: streak.weeks === 1 ? "1 Woche" : `${streak.weeks} Wochen`,
    litFlames: Math.min(streak.weeks, TOTAL_FLAMES),
    totalFlames: TOTAL_FLAMES,
    dimmed: false,
  };

  switch (streak.status) {
    case "active":
      return { ...base, note: "Dein Vergleich für diese Woche ist erledigt." };
    case "pending":
      return { ...base, note: "Diese Woche ist noch offen — ein Vergleich hält deine Streak am Laufen." };
    case "paused":
      return {
        ...base,
        dimmed: true,
        note: `Deine Streak pausiert bei ${base.label}. Mit dem nächsten Vergleich geht es weiter.`,
      };
    case "none":
      return { ...base, note: "Mach deinen ersten Vergleich, um deine Streak zu starten." };
  }
}
