"use client";

import { useState } from "react";
import type { ChatProposal } from "@/lib/assistantChat";
import type {
  ItemRef,
  PreferenceListKey,
  Proposal,
  ProposalChanges,
  ProposalDecision,
} from "@/lib/assistantApi";
import { PREFERENCE_LIST_KEYS, ProposalDraft, startEditing, toChanges } from "@/lib/proposalEdit";
import type { ShoppingListItem } from "@/lib/shoppingList";
import styles from "./ProposalCard.module.css";

const TITLES: Record<Proposal["kind"], string> = {
  shopping_list: "Vorschlag: Einkaufsliste anpassen",
  preferences: "Vorschlag: Präferenzen anpassen",
  location: "Vorschlag: Standort ändern",
};

const PREFERENCE_LABELS: Record<PreferenceListKey, string> = {
  preferred_brands: "Bevorzugte Marken",
  excluded_ingredients: "Ausgeschlossene Zutaten",
  excluded_stores: "Ausgeschlossene Läden",
};

const OUTCOME_LABELS = {
  accepted: "Übernommen",
  rejected: "Verworfen",
  stale: "Nicht mehr gültig",
} as const;

const label = (item: ItemRef) => (item.brand ? `${item.brand} ${item.name}` : item.name);

function ProposalDiff({ proposal }: { proposal: Proposal }) {
  switch (proposal.kind) {
    case "shopping_list": {
      const { added, removed, changed, unchanged } = proposal.diff;
      return (
        <>
          <ul className={styles.diff}>
            {added.map((item) => (
              <li key={`+${item.id}`} className={styles.added}>
                + {label(item)} × {item.quantity}
              </li>
            ))}
            {removed.map((item) => (
              <li key={`-${item.id}`} className={styles.removed}>
                − {label(item)}
              </li>
            ))}
            {changed.map((item) => (
              <li key={`~${item.id}`} className={styles.changed}>
                ~ {label(item)}
                {item.changes.quantity &&
                  `: Menge ${item.changes.quantity.before} → ${item.changes.quantity.after}`}
                {item.changes.category &&
                  `: Kategorie ${item.changes.category.before ?? "–"} → ${item.changes.category.after ?? "–"}`}
              </li>
            ))}
          </ul>
          {unchanged.length > 0 && (
            <p className={styles.muted}>Unverändert: {unchanged.map(label).join(", ")}</p>
          )}
        </>
      );
    }
    case "preferences": {
      const { favorites, ...lists } = proposal.diff;
      return (
        <ul className={styles.diff}>
          {PREFERENCE_LIST_KEYS.map((key) => {
            const part = lists[key];
            return (
              part && (
                <li key={key}>
                  <strong>{PREFERENCE_LABELS[key]}</strong>
                  {part.added.length > 0 && <span className={styles.added}> + {part.added.join(", ")}</span>}
                  {part.removed.length > 0 && (
                    <span className={styles.removed}> − {part.removed.join(", ")}</span>
                  )}
                </li>
              )
            );
          })}
          {favorites && (
            <li>
              <strong>Favoriten</strong>
              {favorites.added.length > 0 && (
                <span className={styles.added}> + {favorites.added.map(label).join(", ")}</span>
              )}
              {favorites.removed.length > 0 && (
                <span className={styles.removed}> − {favorites.removed.map(label).join(", ")}</span>
              )}
            </li>
          )}
        </ul>
      );
    }
    case "location": {
      const { before, after } = proposal.diff;
      return (
        <p className={styles.location}>
          Standort: {before ? `PLZ ${before.zip_code}` : "unbekannt"} → <strong>PLZ {after.zip_code}</strong>
        </p>
      );
    }
  }
}

function ProposalEditor({
  draft,
  onChange,
  listItems,
}: {
  draft: ProposalDraft;
  onChange: (draft: ProposalDraft) => void;
  listItems: ShoppingListItem[];
}) {
  switch (draft.kind) {
    case "shopping_list":
      return (
        <ul className={styles.editor}>
          {draft.rows.map((row, index) => {
            const update = (patch: Partial<typeof row>) =>
              onChange({
                ...draft,
                rows: draft.rows.map((other, i) => (i === index ? { ...other, ...patch } : other)),
              });
            return (
              <li key={row.id} className={row.removed ? styles.struck : undefined}>
                <span className={styles.rowName}>{label(row)}</span>
                <input
                  type="number"
                  min={1}
                  max={999}
                  value={row.quantity}
                  aria-label={`Menge ${label(row)}`}
                  disabled={row.removed}
                  onChange={(event) => update({ quantity: event.target.valueAsNumber })}
                />
                <label>
                  <input
                    type="checkbox"
                    checked={row.removed}
                    onChange={(event) => update({ removed: event.target.checked })}
                  />{" "}
                  entfernen
                </label>
              </li>
            );
          })}
          {draft.rows.length === 0 && <li className={styles.muted}>Die Liste wäre leer.</li>}
        </ul>
      );
    case "preferences":
      return (
        <div className={styles.editor}>
          {PREFERENCE_LIST_KEYS.map(
            (key) =>
              draft.lists[key] !== undefined && (
                <label key={key} className={styles.field}>
                  {PREFERENCE_LABELS[key]} (mit Komma getrennt)
                  <input
                    type="text"
                    value={draft.lists[key]}
                    onChange={(event) =>
                      onChange({ ...draft, lists: { ...draft.lists, [key]: event.target.value } })
                    }
                  />
                </label>
              )
          )}
          {draft.favorites && (
            <fieldset className={styles.field}>
              <legend>Favoriten</legend>
              {listItems.map((item) => (
                <label key={item.id}>
                  <input
                    type="checkbox"
                    checked={draft.favorites!.includes(item.id)}
                    onChange={(event) =>
                      onChange({
                        ...draft,
                        favorites: event.target.checked
                          ? [...draft.favorites!, item.id]
                          : draft.favorites!.filter((id) => id !== item.id),
                      })
                    }
                  />{" "}
                  {label(item)}
                </label>
              ))}
            </fieldset>
          )}
        </div>
      );
    case "location":
      return (
        <label className={styles.field}>
          Postleitzahl
          <input
            type="text"
            inputMode="numeric"
            maxLength={4}
            value={draft.zipCode}
            onChange={(event) => onChange({ ...draft, zipCode: event.target.value })}
          />
        </label>
      );
  }
}

/**
 * A change the assistant proposes: the full diff first, then exactly three reactions —
 * Übernehmen, Ändern (opens an edit state that answers with a fresh diff) and Verwerfen.
 * The look is deliberately plain; the final form comes from the design folder.
 */
export function ProposalCard({
  entry,
  listItems,
  onDecide,
  onRevise,
}: {
  entry: ChatProposal;
  /** The account's current list, for choosing favorites while editing. */
  listItems: ShoppingListItem[];
  onDecide: (decision: ProposalDecision) => void;
  onRevise: (changes: ProposalChanges) => Promise<boolean>;
}) {
  const { proposal, busy, error } = entry;
  const [draft, setDraft] = useState<ProposalDraft | null>(null);
  const open = proposal.status === "pending";

  async function submitEdit() {
    if (!draft) return;
    if (await onRevise(toChanges(draft))) setDraft(null);
  }

  return (
    <section className={styles.card} aria-label={TITLES[proposal.kind]}>
      <h3>{TITLES[proposal.kind]}</h3>
      {draft ? (
        <ProposalEditor draft={draft} onChange={setDraft} listItems={listItems} />
      ) : (
        <ProposalDiff proposal={proposal} />
      )}

      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}

      {!open && (
        <p className={styles.outcome} role="status">
          {OUTCOME_LABELS[proposal.status as keyof typeof OUTCOME_LABELS]}
        </p>
      )}

      {open && !draft && (
        <div className={styles.actions}>
          <button type="button" className={styles.primary} disabled={busy} onClick={() => onDecide("accept")}>
            Übernehmen
          </button>
          <button type="button" disabled={busy} onClick={() => setDraft(startEditing(proposal))}>
            Ändern
          </button>
          <button type="button" disabled={busy} onClick={() => onDecide("reject")}>
            Verwerfen
          </button>
        </div>
      )}

      {open && draft && (
        <div className={styles.actions}>
          <button type="button" className={styles.primary} disabled={busy} onClick={submitEdit}>
            Neuen Vorschlag anzeigen
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              setDraft(null);
            }}
          >
            Abbrechen
          </button>
        </div>
      )}
    </section>
  );
}
