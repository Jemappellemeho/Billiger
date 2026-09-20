import { beforeEach, describe, expect, test } from "vitest";
import { clearSession, loadSession, saveSession } from "./sessionStorage";

describe("account session persistence", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  test("a saved session is readable again until it is cleared", () => {
    saveSession({ token: "t1", email: "anna@example.com" });
    expect(loadSession()).toEqual({ token: "t1", email: "anna@example.com" });

    clearSession();
    expect(loadSession()).toBeNull();
  });

  test("with nothing saved there is no session", () => {
    expect(loadSession()).toBeNull();
  });

  test("corrupted or malformed storage counts as signed out instead of throwing", () => {
    localStorage.setItem("billiger:session", "{not valid json");
    expect(loadSession()).toBeNull();

    localStorage.setItem("billiger:session", JSON.stringify({ email: "no-token@example.com" }));
    expect(loadSession()).toBeNull();
  });
});
