import 'package:familienhub/screens/today/today_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers.dart';

void main() {
  setUp(setUpTestEnv);

  Map<String, dynamic> todayWithHouse(Map<String, dynamic> house) => {
        'date': '2026-10-15',
        'house': house,
        'meals': [
          {'source': 'hub', 'title': 'Kartoffelsuppe'},
        ],
      };

  testWidgets('house card shows selected states with names and units', (tester) async {
    await setScreenSize(tester, const Size(400, 1400));
    final backend = FakeBackend();
    addDefaults(backend);
    backend.json('GET', '/api/today', todayWithHouse({
      'status': 'ok',
      'items': [
        {'entity_id': 'sensor.room', 'name': 'Kinderzimmer', 'state': '21.5', 'unit': '°C'},
        {'entity_id': 'binary_sensor.monitor', 'name': 'Babyphon', 'state': 'on'},
        {'entity_id': 'sensor.washer', 'name': 'Waschmaschine', 'state': 'Fertig'},
      ],
    }));
    await tester.pumpWidget(appWith(backend.api(), const TodayScreen()));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('today-house')), findsOneWidget);
    expect(find.text('Haus'), findsOneWidget);
    expect(find.text('Kinderzimmer'), findsOneWidget);
    expect(find.text('21.5 °C'), findsOneWidget);
    expect(find.text('Babyphon'), findsOneWidget);
    expect(find.text('An'), findsOneWidget);
    expect(find.text('Fertig'), findsOneWidget);
    expect(find.text('Kartoffelsuppe'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  for (final house in [null, {'status': 'not_configured', 'items': []}]) {
    testWidgets('house card hidden when absent or not configured: $house', (tester) async {
      final backend = FakeBackend();
      addDefaults(backend);
      backend.json('GET', '/api/today', house == null ? {} : todayWithHouse(house));
      await tester.pumpWidget(appWith(backend.api(), const TodayScreen()));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('today-house')), findsNothing);
    });
  }

  for (final items in [
    <Map<String, dynamic>>[],
    [
      {'entity_id': 'sensor.room', 'name': 'Kinderzimmer', 'state': '21.5', 'unit': '°C'},
      {'entity_id': 'binary_sensor.monitor', 'name': 'Babyphon', 'state': null},
    ],
  ]) {
    testWidgets('house outage keeps other cards and available states: ${items.length}', (tester) async {
      await setScreenSize(tester, const Size(400, 1400));
      final backend = FakeBackend();
      addDefaults(backend);
      backend.json('GET', '/api/today', todayWithHouse({
        'status': 'unavailable', 'error': 'HA nicht erreichbar', 'items': items,
      }));
      await tester.pumpWidget(appWith(backend.api(), const TodayScreen()));
      await tester.pumpAndSettle();
      expect(find.text('Haus-Zustände gerade nicht verfügbar'), findsOneWidget);
      expect(find.text('Kartoffelsuppe'), findsOneWidget);
      if (items.isNotEmpty) {
        expect(find.text('21.5 °C'), findsOneWidget);
        expect(find.text('Nicht verfügbar'), findsOneWidget);
      }
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('house snapshot uses existing offline banner', (tester) async {
    await setScreenSize(tester, const Size(400, 1400));
    final backend = FakeBackend();
    addDefaults(backend);
    backend.json('GET', '/api/today', todayWithHouse({
      'status': 'ok', 'items': [
        {'entity_id': 'binary_sensor.monitor', 'name': 'Babyphon', 'state': 'off'},
      ],
    }));
    final api = backend.api();
    await api.today();
    backend.offline = true;
    await tester.pumpWidget(appWith(api, const TodayScreen()));
    await tester.pumpAndSettle();
    expect(tester.widget<Tooltip>(find.byKey(const Key('read-status'))).message, startsWith('Offline, Stand '));
    expect(find.text('Babyphon'), findsOneWidget);
    expect(find.text('Aus'), findsOneWidget);
  });
}
