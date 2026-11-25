/* The sidebar asking the Agreements module to show one of its pages, and the
 * module saying which page it is on. The same two-way mechanism as
 * lib/documentsNav.js: a request is left PENDING for a module that is not
 * mounted yet, and consumed once.
 *
 * The page list lived in the module's own inner sidebar until 2026-10-11; it
 * now sits under "Agreements" in the client sidebar, as Documents' does. */
export const AGREEMENTS_VIEW_EVENT = "attorney:agreements-view";
export const AGREEMENTS_SHOWN_EVENT = "attorney:agreements-shown";

/* Whether the DIY builder (Templates, Create) is on is the SERVER's switch
 * (agreements_diy_builder_enabled), read at run time by
 * components/client/useAgreementBuilder.js. There is no frontend copy: a
 * build-time variable here could disagree with the server (2026-11-25). */

export const AGREEMENTS_VIEWS = ["dashboard", "templates", "create", "all"];

let pending = null;

export function requestAgreementsView(view) {
    if (!AGREEMENTS_VIEWS.includes(view)) return;
    pending = view;
    if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent(AGREEMENTS_VIEW_EVENT, { detail: { view } }));
    }
}

export function takePendingAgreementsView() {
    const view = pending;
    pending = null;
    return view;
}

export function announceAgreementsView(view) {
    if (typeof window === "undefined" || !AGREEMENTS_VIEWS.includes(view)) return;
    window.dispatchEvent(new CustomEvent(AGREEMENTS_SHOWN_EVENT, { detail: { view } }));
}
