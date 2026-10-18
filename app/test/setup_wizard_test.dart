import 'package:familienhub/providers/providers.dart';
import 'package:familienhub/screens/admin/admin_screen.dart';
import 'package:familienhub/screens/auth/login_screen.dart';
import 'package:familienhub/screens/more/plugins_admin_screen.dart';
import 'package:familienhub/screens/setup/setup_wizard_screen.dart';
import 'package:familienhub/services/session_store.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

final _ha = {
  'id': 'homeassistant', 'name': 'Home Assistant', 'description': 'Einkauf und Haus', 'configured': false,
  'disabled': false, 'active': false,
  'fields': [
    {'key': 'HOMEASSISTANT_URL', 'label': 'Adresse', 'secret': false, 'required': true, 'help': '', 'value': '', 'is_set': false},
    {'key': 'HOMEASSISTANT_TOKEN', 'label': 'Token', 'secret': true, 'required': true, 'help': '', 'value': '', 'is_set': false},
  ],
};

FakeBackend _backend({bool needsSetup = true}) {
  final b = FakeBackend();
  addDefaults(b);
  b.json('GET', '/api/health', {'status': 'ok', 'oidc': false});
  b.json('GET', '/api/setup/status', {'needs_setup': needsSetup, 'app_name': 'Familienhub', 'oidc': false});
  b.json('GET', '/api/admin/core', {'app_name': 'Familienhub', 'timezone': 'Europe/Berlin'});
  b.json('PUT', '/api/admin/core', {'app_name': 'Familie Beispiel', 'timezone': 'Europe/Vienna'});
  b.json('GET', '/api/admin/settings', [_ha]);
  b.json('GET', '/api/admin/users', [
    {'id': 1, 'username': 'chef', 'display_name': 'Chef', 'role': 'admin', 'is_active': true, 'links': {}},
  ]);
  Map<String, dynamic> src(String id, String name, {bool fallback = false, bool selected = false, bool configured = true}) =>
      {'id': id, 'name': name, 'description': '', 'fallback': fallback, 'configured': configured, 'active': configured, 'selected': selected};
  b.json('GET', '/api/admin/sources', {'areas': [
    {'area': 'tasks', 'multiple': true, 'sources': [src('hub_tasks', 'Aufgaben im Hub', fallback: true, selected: true),
      src('nextcloud', 'CalDAV', configured: false)]},
    {'area': 'shopping', 'multiple': false, 'sources': [src('hub_shopping', 'Einkaufsliste im Hub', fallback: true, selected: true),
      src('homeassistant', 'Home Assistant', configured: false)]},
    {'area': 'calendar', 'multiple': true, 'sources': [src('hub_calendar', 'Familienkalender im Hub', fallback: true, selected: true)]},
  ]});
  b.json('PUT', '/api/admin/sources', {'areas': []});
  return b;
}

void main() {
  setUp(setUpTestEnv);

  testWidgets('Neuer Hub: Einrichten statt Anmelden, erstes Konto startet den Assistenten', (tester) async {
    await setScreenSize(tester, const Size(420, 1600));
    final b = _backend();
    b.on('POST', '/api/setup/admin', (r) {
      final body = bodyOf(r);
      if (body['code'] != 'ABCD-EFGH') return jsonResponse({'detail': 'Einrichtungscode stimmt nicht (steht im Server-Log)'}, status: 403);
      return jsonResponse({'access_token': 'a1', 'refresh_token': 'r1', 'user': {...meJson, 'username': 'chef'}}, status: 201);
    });
    final api = b.api(store: MemorySessionStore(url: 'https://hub.test'));
    await tester.pumpWidget(appWith(api, const LoginScreen()));
    await tester.pumpAndSettle();
    expect(find.text('Einrichten'), findsOneWidget);
    expect(find.text('Benutzername oder Passwort falsch'), findsNothing);
    expect(find.widgetWithText(TextField, 'Passwort wiederholen'), findsOneWidget);

    Future<void> fill(String code) async {
      await tester.enterText(find.byKey(const Key('setup-code')), code);
      await tester.enterText(find.byKey(const Key('setup-name')), 'Chef');
      await tester.enterText(find.byKey(const Key('setup-username')), 'Chef');
      await tester.enterText(find.byKey(const Key('setup-email')), 'chef@example.org');
      await tester.enterText(find.byKey(const Key('setup-password')), 'lang-genug-123');
      await tester.enterText(find.byKey(const Key('setup-repeat')), 'lang-genug-123');
    }

    await fill('ABCD');
    await tester.tap(find.byKey(const Key('setup-submit')));
    await tester.pumpAndSettle();
    expect(find.textContaining('Einrichtungscode aus dem Server-Log'), findsOneWidget);
    expect(b.sent('POST', '/api/setup/admin'), isEmpty);

    await fill('WXYZ-WXYZ');
    await tester.tap(find.byKey(const Key('setup-submit')));
    await tester.pumpAndSettle();
    expect(find.textContaining('Einrichtungscode stimmt nicht'), findsOneWidget);

    await fill('ABCD-EFGH');
    await tester.tap(find.byKey(const Key('setup-submit')));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('POST', '/api/setup/admin').last), {
      'code': 'ABCD-EFGH', 'username': 'chef', 'email': 'chef@example.org', 'password': 'lang-genug-123',
      'display_name': 'Chef', 'client': 'app',
    });
    final session = ProviderScope.containerOf(tester.element(find.byType(LoginScreen))).read(sessionProvider);
    expect(session.phase, SessionPhase.loggedIn);
    expect(session.onboarding, isTrue);
    expect(await api.store.accessToken(), 'a1');
  });

  testWidgets('Eingerichteter Hub zeigt die normale Anmeldung', (tester) async {
    final b = _backend(needsSetup: false);
    await tester.pumpWidget(appWith(b.api(store: MemorySessionStore(url: 'https://hub.test')), const LoginScreen()));
    await tester.pumpAndSettle();
    expect(find.text('Anmelden'), findsWidgets);
    expect(find.byKey(const Key('setup-code')), findsNothing);
  });

  testWidgets('Assistent: Name und Zeitzone speichern, Dienste, Familie, Fertig', (tester) async {
    await setScreenSize(tester, const Size(420, 1200));
    final b = _backend();
    await tester.pumpWidget(appWith(b.api(), const SetupWizardScreen(standalone: true)));
    await tester.pumpAndSettle();
    expect(tester.widget<TextField>(find.byKey(const Key('wizard-app-name'))).controller!.text, 'Familienhub');
    await tester.enterText(find.byKey(const Key('wizard-app-name')), 'Familie Beispiel');
    await tester.enterText(find.byKey(const Key('wizard-timezone')), 'Europe/Vienna');
    await tester.tap(find.byKey(const Key('wizard-next')));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('PUT', '/api/admin/core').single), {'app_name': 'Familie Beispiel', 'timezone': 'Europe/Vienna'});

    // New step "Bereiche" (18.10.): everything in the hub by default
    expect(find.text('Im Hub'), findsNWidgets(3));
    await tester.tap(find.byKey(const Key('wizard-next')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('wizard-plugin-homeassistant')), findsOneWidget);
    expect(find.text('Einrichten'), findsOneWidget);
    await tester.tap(find.byKey(const Key('wizard-next')));
    await tester.pumpAndSettle();
    expect(find.text('Chef'), findsOneWidget);
    expect(find.byKey(const Key('wizard-add-person')), findsOneWidget);
    await tester.tap(find.byKey(const Key('wizard-next')));
    await tester.pumpAndSettle();
    expect(find.text('Fertig eingerichtet'), findsOneWidget);
    expect(find.textContaining('Noch keine Dienste verbunden'), findsOneWidget);
  });

  testWidgets('Assistent nach dem ersten Konto: „Los geht’s“ beendet die Einrichtung', (tester) async {
    await setScreenSize(tester, const Size(420, 1200));
    final b = _backend();
    final api = b.api();
    final container = ProviderContainer(overrides: [apiClientProvider.overrideWithValue(api)]);
    addTearDown(container.dispose);
    container.read(sessionProvider.notifier).state =
        const SessionState(SessionPhase.loggedIn, user: null, onboarding: true);
    await tester.pumpWidget(UncontrolledProviderScope(
      container: container,
      child: const MaterialApp(locale: Locale('de', 'DE'), home: SetupWizardScreen()),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('wizard-skip')));
    await tester.pumpAndSettle();
    expect(container.read(sessionProvider).onboarding, isFalse);
  });

  testWidgets('Verbindung testen: eingegebene Werte, Ergebnis sichtbar, Geheimnis leer = gespeichert', (tester) async {
    await setScreenSize(tester, const Size(420, 1200));
    final b = _backend();
    b.on('POST', '/api/admin/plugins/homeassistant/test', (r) {
      final values = bodyOf(r)['values'] as Map;
      return jsonResponse(values['HOMEASSISTANT_TOKEN'] == 'gut'
          ? {'ok': true, 'level': 'ok', 'message': 'Home Assistant: verbunden, Token gültig'}
          : {'ok': false, 'level': 'error', 'message': 'Home Assistant erreichbar, aber Token ungültig'});
    });
    final plugin = (await b.api().adminPlugins()).single;
    await tester.pumpWidget(appWith(b.api(), PluginSettingsScreen(plugin: plugin)));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('field-HOMEASSISTANT_URL')), 'http://ha.local:8123');
    await tester.enterText(find.byKey(const Key('field-HOMEASSISTANT_TOKEN')), 'falsch');
    await tester.tap(find.byKey(const Key('plugin-test')));
    await tester.pumpAndSettle();
    expect(find.text('Home Assistant erreichbar, aber Token ungültig'), findsOneWidget);
    await tester.enterText(find.byKey(const Key('field-HOMEASSISTANT_TOKEN')), 'gut');
    await tester.pump();
    expect(find.byKey(const Key('plugin-test-result')), findsNothing, reason: 'altes Ergebnis verschwindet bei Änderung');
    await tester.tap(find.byKey(const Key('plugin-test')));
    await tester.pumpAndSettle();
    expect(find.text('Home Assistant: verbunden, Token gültig'), findsOneWidget);
    expect(bodyOf(b.sent('POST', '/api/admin/plugins/homeassistant/test').last), {
      'values': {'HOMEASSISTANT_URL': 'http://ha.local:8123', 'HOMEASSISTANT_TOKEN': 'gut'},
    });
    expect(b.sent('PUT', '/api/admin/settings'), isEmpty, reason: 'Testen speichert nichts');
  });

  testWidgets('Verwaltung bietet den Assistenten erneut an', (tester) async {
    await setScreenSize(tester, const Size(420, 1600));
    final b = _backend();
    b.json('GET', '/api/admin/overview', {'server': {'version': '1'}, 'plugins': [], 'push': {}, 'users': {'active': 1}});
    await tester.pumpWidget(appWith(b.api(), const AdminScreen()));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('admin-wizard')), findsOneWidget);
  });
}
