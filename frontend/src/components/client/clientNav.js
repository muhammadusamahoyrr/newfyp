"use client";
import { createContext, startTransition, useContext, useMemo } from "react";
import { useRouter } from "next/navigation";
import { tabForPath } from "./clientRoutes.js";

// Provided by Dashboard: `show(tab)` switches the visible client screen now.
export const ClientNavCtx = createContext(null);

// The client screen an href shows AT ONCE, or null when it must wait for the URL.
// An href with a query string waits: the screen it opens reads that query
// (e.g. /lawyers?case_id=…) when it mounts, so showing it before the URL has
// changed would hand it the old one.
export function instantTabFor(href) {
    if (typeof href !== "string" || /[?#]/.test(href)) return null;
    return tabForPath(href);
}

/**
 * next/navigation's router, except that push() shows the target client screen
 * immediately and lets the URL follow in a transition. Plain router.push left
 * the old screen up until the route change finished — in development that
 * includes compiling a route on its first visit, which read as a frozen click.
 * Outside the client app (no provider, e.g. tests) it is the plain router.
 */
export function useClientRouter() {
    const router = useRouter();
    const nav = useContext(ClientNavCtx);
    return useMemo(() => {
        if (!nav) return router;
        return {
            ...router,
            push: (href, opts) => {
                const tab = instantTabFor(href);
                if (tab) nav.show(tab);
                startTransition(() => router.push(href, opts));
            },
        };
    }, [router, nav]);
}
