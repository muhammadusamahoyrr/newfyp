/* Is the client agreement builder on? THE SERVER SAYS (2026-11-25).
 *
 * It used to be a build-time variable (NEXT_PUBLIC_AGREEMENTS_DIY_ENABLED)
 * beside the server's own setting (agreements_diy_builder_enabled), and the
 * two could disagree: the builder hidden while the server allowed it, or shown
 * while the server refused the send with a 403 at the very last click. Now
 * there is one switch, on the server, read from GET /agreements/capabilities.
 *
 * null = still asking; false on any failure (fail closed: hide, never offer
 * what may be refused). Only a real answer is remembered, so a failed read
 * (e.g. before sign-in) is asked again by the next screen. */
import { useEffect, useState } from "react";
import { getAgreementCapabilities } from "@/lib/api.js";

let known = null;
let inflight = null;

export function askAgreementBuilder() {
    if (known !== null) return Promise.resolve(known);
    if (!inflight) {
        inflight = Promise.resolve()
            .then(() => getAgreementCapabilities())
            .then(r => {
                inflight = null;
                const on = r?.data?.diy_builder;
                if (!r?.error && typeof on === "boolean") { known = on; return on; }
                return false;
            }, () => { inflight = null; return false; });
    }
    return inflight;
}

export function useAgreementBuilderOn() {
    const [on, setOn] = useState(known);
    useEffect(() => {
        let live = true;
        askAgreementBuilder().then(v => { if (live) setOn(v); });
        return () => { live = false; };
    }, []);
    return on;
}

/** Tests only: forget the remembered answer. */
export function __resetAgreementBuilder() { known = null; inflight = null; }
