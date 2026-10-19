# Import recipes from a link

In the recipe book (Meals > Recipe book) tap the link icon, paste the address of a recipe page and tap
"Read recipe". The hub fetches the page itself and reads the structured recipe data (schema.org `Recipe`
as JSON-LD, including `@graph`, arrays and nested objects, with microdata as a fallback). You get the
recipe in the normal editor: title, picture, servings, time, ingredients, steps and the source link.
Check and edit it, then tap "Save". Nothing is stored before that. Afterwards it behaves like any hub recipe
(plan it on a day, put the ingredients on the shopping list).

- Pages without recipe data show a message and nothing is saved.
- Times are read from ISO 8601 durations (`PT1H30M`); if there is no total time, preparation and cooking time are added.
- Steps in sections (`HowToSection`) keep their headings as separate lines.
- The picture is kept as a link to the image on the source site (like the source link); it is not copied
  to the hub. If the site removes the image, the recipe simply shows none.

## Safety

The hub fetches the address, so it is restricted: only `http`/`https` on the default ports, a 10 second
timeout, at most 2 MB and 4 redirects. The address and every redirect target must resolve to public
addresses only; loopback, private, link-local (for example cloud metadata) and other internal ranges are
refused. Adding or changing recipes requires the partner role or higher.

## Share into the app

The web app (PWA) declares a share target in its manifest: after installing it, "Share" in the browser can
send a recipe page to Familienhub, which opens "Import from link" with that address. This depends on the
browser (Chrome on Android supports it for installed PWAs). A share entry in the native Android app
needs a separate intent filter and plugin and is not part of this yet.
