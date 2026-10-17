/// Nicht-Web: keine Browser-Funktionen.
bool get webPushSupported => false;

/// 'granted', 'denied', 'default' oder null, wenn nicht unterstützt.
String? webPushPermission() => null;

/// Läuft als installierte App (Home-Bildschirm)? Auf iOS Voraussetzung für Web Push.
bool isStandalone() => false;

Future<Map<String, dynamic>?> subscribeWebPush(String vapidPublicKey, {bool prompt = true}) async => null;

Stream<String> serviceWorkerRoutes() => const Stream.empty();

/// Query-Parameter der Startadresse (z. B. `oidc_code`, `route`).
Map<String, String> startQuery() => const {};

/// Entfernt Query-Parameter aus der Adresszeile, ohne neu zu laden.
void clearStartQuery() {}

/// Herkunft der Seite, z. B. `https://hub.example.org` (nur Web).
String? pageOrigin() => null;
