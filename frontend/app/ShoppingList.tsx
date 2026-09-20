"use client";

import { FormEvent, useState } from "react";
import { useShoppingList } from "@/hooks/useShoppingList";
import {
  MAX_CATEGORY_LENGTH,
  MAX_NAME_LENGTH,
  MAX_PREFERENCE_LENGTH,
  MAX_QUANTITY,
  ShoppingListItem,
} from "@/lib/shoppingList";
import styles from "./ShoppingList.module.css";

export type ShoppingListController = ReturnType<typeof useShoppingList>;

function groupByCategory(items: ShoppingListItem[]) {
  const groups = new Map<string, ShoppingListItem[]>();
  for (const item of items) {
    const key = item.category ?? "Ohne Kategorie";
    groups.set(key, [...(groups.get(key) ?? []), item]);
  }
  return groups;
}

function TagList({
  label,
  values,
  onAdd,
  onRemove,
}: {
  label: string;
  values: string[];
  onAdd: (value: string) => void;
  onRemove: (value: string) => void;
}) {
  const [input, setInput] = useState("");

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!input.trim()) return;
    onAdd(input.trim());
    setInput("");
  }

  return (
    <div className={styles.preferenceGroup}>
      <span className={styles.preferenceLabel}>{label}</span>
      <form onSubmit={handleSubmit} className={styles.row}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          maxLength={MAX_PREFERENCE_LENGTH}
          aria-label={label}
        />
        <button type="submit">Hinzufügen</button>
      </form>
      {values.length > 0 && (
        <ul className={styles.tagList}>
          {values.map((value) => (
            <li key={value} className={styles.tag}>
              {value}
              <button
                type="button"
                aria-label={`${value} entfernen`}
                onClick={() => onRemove(value)}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function ShoppingListView({ list }: { list: ShoppingListController }) {
  const [nameInput, setNameInput] = useState("");

  function handleAddByName(event: FormEvent) {
    event.preventDefault();
    if (!nameInput.trim()) return;
    list.addItem({ name: nameInput.trim() });
    setNameInput("");
  }

  const groups = groupByCategory(list.items);

  return (
    <section className={styles.section}>
      <h2>Einkaufsliste</h2>

      <form onSubmit={handleAddByName} className={styles.row}>
        <input
          type="text"
          placeholder="Artikel per Name hinzufügen"
          value={nameInput}
          onChange={(e) => setNameInput(e.target.value)}
          maxLength={MAX_NAME_LENGTH}
          aria-label="Artikel per Name hinzufügen"
        />
        <button type="submit">Hinzufügen</button>
      </form>

      {list.items.length === 0 && <p className={styles.empty}>Deine Liste ist leer.</p>}

      {[...groups.entries()].map(([category, items]) => (
        <div key={category} className={styles.categoryGroup}>
          <h3>{category}</h3>
          <ul className={styles.itemList}>
            {items.map((item) => (
              <li key={item.id} className={styles.item}>
                <button
                  type="button"
                  className={styles.favoriteButton}
                  aria-label={item.favorite ? "Favorit entfernen" : "Als Favorit markieren"}
                  aria-pressed={item.favorite}
                  onClick={() => list.toggleFavorite(item.id)}
                >
                  {item.favorite ? "★" : "☆"}
                </button>
                <span className={styles.itemName}>
                  {item.brand && <strong>{item.brand} </strong>}
                  {item.name}
                </span>
                <input
                  type="number"
                  min={1}
                  max={MAX_QUANTITY}
                  value={item.quantity}
                  aria-label={`Menge für ${item.name}`}
                  onChange={(e) => list.setQuantity(item.id, Number(e.target.value))}
                  className={styles.quantityInput}
                />
                <input
                  type="text"
                  placeholder="Kategorie"
                  maxLength={MAX_CATEGORY_LENGTH}
                  defaultValue={item.category ?? ""}
                  aria-label={`Kategorie für ${item.name}`}
                  onBlur={(e) => list.setCategory(item.id, e.target.value.trim() || null)}
                  className={styles.categoryInput}
                />
                <button
                  type="button"
                  aria-label={`${item.name} entfernen`}
                  onClick={() => list.removeItem(item.id)}
                >
                  Entfernen
                </button>
              </li>
            ))}
          </ul>
        </div>
      ))}

      <h3 className={styles.preferencesHeading}>Präferenzen</h3>
      <TagList
        label="Bevorzugte Marken"
        values={list.preferences.preferredBrands}
        onAdd={(value) => list.addPreference("preferredBrands", value)}
        onRemove={(value) => list.removePreference("preferredBrands", value)}
      />
      <TagList
        label="Ausgeschlossene Zutaten"
        values={list.preferences.excludedIngredients}
        onAdd={(value) => list.addPreference("excludedIngredients", value)}
        onRemove={(value) => list.removePreference("excludedIngredients", value)}
      />
      <TagList
        label="Ausgeschlossene Läden"
        values={list.preferences.excludedStores}
        onAdd={(value) => list.addPreference("excludedStores", value)}
        onRemove={(value) => list.removePreference("excludedStores", value)}
      />
    </section>
  );
}
