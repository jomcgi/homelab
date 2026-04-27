// Single source of truth for the cross-domain nav.
//
// When `notes` becomes public, change the second link's href to a
// relative `/notes` path and serve from the public origin.
export const NAV_LINKS = [
  { label: "home", href: "https://public.jomcgi.dev/" },
  { label: "notes", href: "https://private.jomcgi.dev/notes" },
];
