import 'package:familienhub/screens/admin/ics_feeds_screen.dart';
import 'package:familienhub/screens/setup/setup_wizard_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

/// Setup wizard "areas" step and calendar subscriptions.
void main() {
  setUp(setUpTestEnv);

  Map<String, dynamic> src(String id, String name, {bool fallback = false, bool selected = false, bool configured = true}) =>
      {'id': id, 'name': name, 'description': '', 'fallback': fallback, 'configured': configured, 'active': configured, 'selected': selected};

  FakeBackend backend({bool haConfigured = false}) {
    final b = FakeBackend();
    addDefaults(b);
    b.json('GET', '/api/admin/core', {'app_name': 'Familienhub', 'timezone': 'Europe/Berlin'});
    b.json('PUT', '/api/admin/core', {'app_name': 'Familienhub', 'timezone': 'Europe/Berlin'});
    b.json('GET', '/api/admin/settings', [
      {'id': 'homeassistant', 'name': 'Home Assistant', 'description': '', 'configured': haConfigured, 'disabled': false,
       'active': haConfigured, 'fields': []},
      {'id': 'weather', 'name': 'Wetter', 'description': '', 'configured': true, 'disabled': false, 'active': true, 'fields': []},
    ]);
    b.json('GET', '/api/admin/users', []);
    b.json('GET', '/api/admin/sources', {'areas': [
      {'area': 'tasks', 'multiple': true, 'sources': [src('hub_tasks', 'Aufgaben im Hub', fallback: true, selected: true)]},
      {'area': 'shopping', 'multiple': false, 'sources': [src('hub_shopping', 'Einkaufsliste im Hub', fallback: true, selected: true),
        src('homeassistant', 'Home Assistant', configured: haConfigured)]},
      {'area': 'calendar', 'multiple': true, 'sources': [src('hub_calendar', 'Familienkalender im Hub', fallback: true, selected: true)]},
    ]});
    b.json('PUT', '/api/admin/sources', {'areas': []});
    return b;
  }

  Future<void> toAreas(WidgetTester tester, FakeBackend b) async {
    await setScreenSize(tester, const Size(420, 1600));
    await tester.pumpWidget(appWith(b.api(), const SetupWizardScreen(standalone: true)));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('wizard-next')));
    await tester.pumpAndSettle();
  }

  Map<String, List> saved(FakeBackend b) =>
      {for (final r in b.sent('PUT', '/api/admin/sources')) bodyOf(r)['area'] as String: bodyOf(r)['selected'] as List};

  testWidgets('choosing Home Assistant puts it on top of the services; set up → used for shopping', (tester) async {
    final b = backend(haConfigured: true);
    await toAreas(tester, b);
    await tester.tap(find.byKey(const Key('area-shopping-homeassistant')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('wizard-next')));
    await tester.pumpAndSettle();
    expect(find.text('Für eure Auswahl einrichten'), findsOneWidget);
    final haY = tester.getTopLeft(find.byKey(const Key('wizard-plugin-homeassistant'))).dy;
    final weatherY = tester.getTopLeft(find.byKey(const Key('wizard-plugin-weather'))).dy;
    expect(haY, lessThan(weatherY));
    await tester.tap(find.byKey(const Key('wizard-next')));
    await tester.pumpAndSettle();
    expect(saved(b), {'tasks': ['hub_tasks'], 'shopping': ['homeassistant'], 'calendar': ['hub_calendar']});
  });

  testWidgets('chosen but not set up: the hub is used and the wizard says so', (tester) async {
    final b = backend();
    await toAreas(tester, b);
    await tester.tap(find.byKey(const Key('area-shopping-homeassistant')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('wizard-next')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('wizard-next')));
    await tester.pumpAndSettle();
    expect(saved(b)['shopping'], ['hub_shopping']);
    expect(find.textContaining('Home Assistant noch nicht eingerichtet'), findsOneWidget);
  });

  testWidgets('calendar subscriptions: add only after a successful check, remove', (tester) async {
    final b = FakeBackend();
    addDefaults(b);
    var feeds = <Map<String, dynamic>>[];
    b.on('GET', '/api/admin/ics', (_) => jsonResponse({'feeds': feeds}));
    b.on('PUT', '/api/admin/ics', (r) {
      feeds = [for (final f in bodyOf(r)['feeds'] as List) Map<String, dynamic>.from(f as Map)];
      return jsonResponse({'feeds': feeds});
    });
    b.on('POST', '/api/admin/ics/test', (r) => jsonResponse((bodyOf(r)['url'] as String).contains('ferien')
        ? {'ok': true, 'error': null, 'events': 12, 'sample': ['Herbstferien']}
        : {'ok': false, 'error': 'Das ist keine Kalenderdatei (ICS)', 'events': 0, 'sample': []}));
    await setScreenSize(tester, const Size(420, 1200));
    await tester.pumpWidget(appWith(b.api(), const IcsFeedsScreen()));
    await tester.pumpAndSettle();
    expect(find.text('Noch keine Kalender abonniert.'), findsOneWidget);

    await tester.tap(find.byKey(const Key('ics-add')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('ics-name')), 'Schulferien');
    await tester.enterText(find.byKey(const Key('ics-url')), 'https://example.org/falsch.html');
    await tester.ensureVisible(find.byKey(const Key('ics-check')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Prüfen'));
    await tester.pumpAndSettle();
    expect(find.text('Das ist keine Kalenderdatei (ICS)'), findsOneWidget);
    expect(tester.widget<FilledButton>(find.byKey(const Key('ics-save'))).onPressed, isNull);

    await tester.enterText(find.byKey(const Key('ics-url')), 'https://example.org/ferien.ics');
    await tester.ensureVisible(find.byKey(const Key('ics-check')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Prüfen'));
    await tester.pumpAndSettle();
    expect(find.text('12 Termine in den nächsten 90 Tagen'), findsOneWidget);
    await tester.tap(find.byKey(const Key('ics-save')));
    await tester.pumpAndSettle();
    expect(feeds, [{'name': 'Schulferien', 'url': 'https://example.org/ferien.ics'}]);
    expect(find.text('Schulferien'), findsOneWidget);

    await tester.tap(find.byTooltip('Entfernen'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Entfernen'));
    await tester.pumpAndSettle();
    expect(feeds, isEmpty);
  });
}
