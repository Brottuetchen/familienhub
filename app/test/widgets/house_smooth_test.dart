import 'dart:async';
import 'dart:convert';

import 'package:familienhub/screens/today/house_controls.dart';
import 'package:familienhub/screens/today/today_screen.dart';
import 'package:familienhub/services/api_client.dart';
import 'package:familienhub/services/session_store.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import '../helpers.dart';
import 'house_controls_test.dart' show tileWith, tapOf;

Map<String, dynamic> _ctl(String id, String name, String state, {List<String>? actions, int? brightness}) => {
      'entity_id': id,
      'name': name,
      'state': state,
      'actions': actions ?? ['turn_on', 'turn_off'],
      'brightness': brightness,
    };

/// Haus-Backend mit echtem Zustand, gehaltenen Aktionen und mitgezählten Lesevorgängen.
class _House {
  final states = <String, String>{'light.lamp': 'off', 'switch.plug': 'off'};
  final held = <String, Completer<http.Response>>{};
  final posts = <String>[];
  var reads = 0;
  bool holdActions = false;
  bool confirmInReply = false;
  bool haIgnoresActions = false;

  Map<String, dynamic> controls() => {
        'status': 'ok',
        'items': [_ctl('light.lamp', 'Lampe', states['light.lamp']!), _ctl('switch.plug', 'Steckdose', states['switch.plug']!)],
      };

  ApiClient api() => ApiClient(
        store: MemorySessionStore(url: 'https://hub.test', access: 'token'),
        httpClient: MockClient((r) async {
          switch (r.url.path) {
            case '/api/auth/me':
              return jsonResponse(meJson);
            case '/api/today':
              return jsonResponse({});
            case '/api/house/controls':
              reads++;
              return jsonResponse(controls());
            case '/api/house/actions':
              final body = jsonDecode(r.body) as Map<String, dynamic>;
              final id = body['entity_id'] as String;
              posts.add(id);
              if (holdActions) {
                held[id] = Completer();
                return held[id]!.future;
              }
              if (!haIgnoresActions) states[id] = body['action'] == 'turn_on' ? 'on' : 'off';
              return jsonResponse({
                'accepted': true,
                'control': confirmInReply ? controls()['items'].firstWhere((c) => c['entity_id'] == id) : null,
              });
          }
          return jsonResponse({}, status: 404);
        }),
      );
}

void main() {
  setUp(setUpTestEnv);

  testWidgets('Kachel schaltet sofort um, andere Kacheln bleiben bedienbar', (tester) async {
    await setScreenSize(tester, const Size(400, 1800));
    final house = _House()..holdActions = true;
    await tester.pumpWidget(appWith(house.api(), const TodayScreen()));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const Key('light.lamp-turn_on')));
    await tester.tap(find.byKey(const Key('light.lamp-turn_on')));
    await tester.pump();
    expect(tileWith('Lampe', 'An'), findsOneWidget, reason: 'sofort, ohne auf HA zu warten');
    expect(find.byType(LinearProgressIndicator), findsNothing);
    expect(tapOf(tester, find.byKey(const Key('light.lamp-turn_on'))), isNull, reason: 'kein zweiter POST fürs selbe Gerät');
    // Steckdose ist trotzdem schaltbar
    await tester.tap(find.byKey(const Key('switch.plug-turn_on')));
    await tester.pump();
    expect(tileWith('Steckdose', 'An'), findsOneWidget);
    expect(house.posts, ['light.lamp', 'switch.plug']);
    house.held['light.lamp']!.complete(jsonResponse({'accepted': true, 'control': _ctl('light.lamp', 'Lampe', 'on')}));
    house.held['switch.plug']!.complete(jsonResponse({'accepted': true, 'control': _ctl('switch.plug', 'Steckdose', 'on')}));
    await tester.pump();
    await tester.pump();
    expect(tileWith('Lampe', 'An'), findsOneWidget);
    expect(tileWith('Steckdose', 'An'), findsOneWidget);
    expect(house.posts, hasLength(2));
  });

  testWidgets('Bestätigung im POST: kein zusätzliches Nachlesen nötig', (tester) async {
    await setScreenSize(tester, const Size(400, 1800));
    final house = _House()..confirmInReply = true;
    await tester.pumpWidget(appWith(house.api(), const TodayScreen()));
    await tester.pumpAndSettle();
    final readsBefore = house.reads;
    await tester.ensureVisible(find.byKey(const Key('light.lamp-turn_on')));
    await tester.tap(find.byKey(const Key('light.lamp-turn_on')));
    await tester.pump();
    await tester.pump();
    expect(tileWith('Lampe', 'An'), findsOneWidget);
    expect(find.byKey(const Key('light.lamp-turn_off')), findsOneWidget, reason: 'bestätigt');
    expect(house.reads, readsBefore);
  });

  testWidgets('Reagiert HA nicht, fällt die Kachel nach der Frist zurück – ohne erneutes Senden', (tester) async {
    await setScreenSize(tester, const Size(400, 1800));
    final house = _House()..haIgnoresActions = true;
    await tester.pumpWidget(appWith(house.api(), const TodayScreen()));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const Key('light.lamp-turn_on')));
    await tester.tap(find.byKey(const Key('light.lamp-turn_on')));
    await tester.pump();
    expect(tileWith('Lampe', 'An'), findsOneWidget);
    await tester.pump(const Duration(seconds: 2));
    expect(tileWith('Lampe', 'An'), findsOneWidget, reason: 'innerhalb der Frist bleibt der erwartete Zustand');
    await tester.pump(const Duration(seconds: 3));
    await tester.pump();
    expect(tileWith('Lampe', 'Aus'), findsOneWidget);
    expect(house.posts, ['light.lamp']);
  });

  testWidgets('Änderungen von außen erscheinen von selbst, ohne dass Kacheln verschwinden', (tester) async {
    await setScreenSize(tester, const Size(400, 1800));
    final house = _House();
    await tester.pumpWidget(appWith(house.api(), const TodayScreen()));
    await tester.pumpAndSettle();
    expect(tileWith('Steckdose', 'Aus'), findsOneWidget);
    expect(find.byTooltip('Haus aktualisieren'), findsNothing, reason: 'kein Knopf im Normalbetrieb');
    house.states['switch.plug'] = 'on'; // z. B. in Home Assistant geschaltet
    await tester.pump(const Duration(seconds: 5));
    expect(find.byType(HouseTile), findsNWidgets(2), reason: 'Kacheln bleiben während des Lesens stehen');
    await tester.pump();
    expect(tileWith('Steckdose', 'An'), findsOneWidget);
    expect(house.posts, isEmpty);
  });

  testWidgets('Datum steht nicht mehr im Kopf', (tester) async {
    final backend = FakeBackend();
    addDefaults(backend);
    await tester.pumpWidget(appWith(backend.api(), const TodayScreen()));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('today-greeting')), findsOneWidget);
    final weekdays = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag'];
    for (final d in weekdays) {
      expect(find.textContaining('$d, '), findsNothing);
    }
  });
}
