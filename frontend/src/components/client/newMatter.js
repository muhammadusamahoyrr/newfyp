/* "New matter" means a NEW intake (2026-10-21).
 *
 * Opening Legal Intake offers to continue an unfinished intake. The "New
 * matter" buttons must not land there: they leave a one-shot flag (read by
 * ModIntake when it mounts) and an event (heard when Legal Intake is already
 * on screen). Kept apart from ModIntake so the sidebar does not import the
 * whole intake screen, which is loaded lazily. */
export const NEW_MATTER_KEY = "attorney:intake-new";
export const NEW_MATTER_EVENT = "attorney:intake-new";

export function requestNewMatter() {
    try { sessionStorage.setItem(NEW_MATTER_KEY, "1"); } catch { /* storage blocked */ }
    if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent(NEW_MATTER_EVENT));
}

/** True once per request: the flag is cleared as it is read. */
export function takeNewMatterRequest() {
    try {
        if (sessionStorage.getItem(NEW_MATTER_KEY) !== "1") return false;
        sessionStorage.removeItem(NEW_MATTER_KEY);
        return true;
    } catch { return false; }
}
