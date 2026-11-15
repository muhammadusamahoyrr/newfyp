// Which client screen (Dashboard tab) each client URL shows, and back.
//
// The client app is mounted ONCE, in app/(client)/layout.jsx, and stays mounted
// while the user moves between these URLs; the URL only picks the visible tab.
// (Each page used to mount its own copy of the whole app, so every sidebar click
// rebuilt the shell, reloaded cases/appointments/notifications and reopened the
// notification socket.)

export const PATH_TAB = {
  "/dashboard": "overview",
  "/intake": "intake",
  "/chat": "chatbot",
  "/lawyers": "lawyers",
  "/documents": "documents",
  "/agreements": "agreements",
  "/tracking": "tracking",
  "/cases": "tracking",
  "/appointments": "appointments",
  "/profile": "profile",
  // Hidden from the sidebar (out of scope, see SIDE_ITEMS) but its URL still opens it.
  "/tools": "tools",
};

export const TAB_PATH = {
  overview: "/dashboard",
  intake: "/intake",
  chatbot: "/chat",
  lawyers: "/lawyers",
  documents: "/documents",
  agreements: "/agreements",
  tracking: "/tracking",
  appointments: "/appointments",
  profile: "/profile",
  tools: "/tools",
};

export const tabForPath = (pathname) => PATH_TAB[pathname] || null;
