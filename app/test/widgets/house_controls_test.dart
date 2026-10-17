import 'dart:async';

import 'package:familienhub/providers/providers.dart';
import 'package:familienhub/services/api_client.dart';
import 'package:familienhub/services/session_store.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:familienhub/screens/today/house_controls.dart';
import 'package:familienhub/screens/today/today_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers.dart';

/// Kachel mit [name] zeigt [value] (vorher Text „name: value“).
Finder tileWith(String name, String value) => find.descendant(
    of: find.ancestor(of: find.text(name), matching: find.byType(HouseTile)),
    matching: find.textContaining(value));

/// Antipp-Aktion der Kachel (vorher OutlinedButton.onPressed).
VoidCallback? tapOf(WidgetTester tester, Finder tile) =>
    tester.widget<InkWell>(find.descendant(of: tile, matching: find.byType(InkWell)).first).onTap;

/// Kacheln, die eine Geräteaktion auslösen würden (Schlüssel endet auf die Aktion).
final actionTiles = find.byWidgetPredicate((w) =>
    w.key is ValueKey<String> && RegExp(r'-(turn_on|turn_off|activate)$').hasMatch((w.key as ValueKey<String>).value));

void main() {
  setUp(setUpTestEnv);

  for (final width in [360.0, 1000.0]) {
    testWidgets('house controls confirm refresh and fit $width', (tester) async {
      await setScreenSize(tester, Size(width, 1800));
      final backend = FakeBackend();
      addDefaults(backend);
      var state = 'off';
      backend.on('GET', '/api/house/controls', (_) => jsonResponse({
        'status': 'ok', 'items': [
          {'entity_id': 'light.lamp', 'name': 'Lampe', 'state': state,
           'actions': ['turn_on', 'turn_off', 'brightness'], 'brightness': 128},
          {'entity_id': 'scene.evening', 'name': 'Abend', 'state': 'ready', 'actions': ['activate']},
        ],
      }));
      backend.on('POST', '/api/house/actions', (request) {
        expect(bodyOf(request), {'entity_id': 'light.lamp', 'action': 'turn_on'});
        state = 'on';
        return jsonResponse({'accepted': true});
      });
      await tester.pumpWidget(appWith(backend.api(), const TodayScreen()));
      await tester.pumpAndSettle();
      expect(tileWith('Lampe', 'Aus'), findsOneWidget);
      expect(find.byType(Slider), findsOneWidget);
      expect(find.byKey(const Key('scene.evening-activate')), findsOneWidget);
      await tester.ensureVisible(find.byKey(const Key('light.lamp-turn_on')));
      await tester.tap(find.byKey(const Key('light.lamp-turn_on')));
      await tester.pumpAndSettle();
      expect(backend.sent('POST', '/api/house/actions'), hasLength(1));
      // Sofort „An“; ohne Bestätigung im POST liest die Karte kurz danach nach
      expect(tileWith('Lampe', 'An'), findsOneWidget);
      await tester.pump(const Duration(seconds: 2));
      expect(backend.sent('GET', '/api/house/controls').length, greaterThanOrEqualTo(2));
      expect(tileWith('Lampe', 'An'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('pending house POST stays single across refresh and failure is visible', (tester) async {
    await setScreenSize(tester, const Size(400, 1800));
    final action = Completer<http.Response>();
    final refresh = Completer<http.Response>();
    var posts = 0;
    var todayReads = 0;
    final api = ApiClient(
      store: MemorySessionStore(url: 'https://hub.test', access: 'token'),
      httpClient: MockClient((request) async {
        if (request.url.path == '/api/house/actions') { posts++; return action.future; }
        if (request.url.path == '/api/today') {
          todayReads++;
          if (todayReads > 1) { return refresh.future; }
          return jsonResponse({});
        }
        if (request.url.path == '/api/auth/me') return jsonResponse(meJson);
        if (request.url.path == '/api/house/controls') {
          return jsonResponse({
            'status': 'ok', 'items': [
              {'entity_id': 'switch.plug', 'name': 'Steckdose', 'state': 'off', 'actions': ['turn_on', 'turn_off']},
            ],
          });
        }
        return jsonResponse({}, status: 404);
      }),
    );
    await tester.pumpWidget(appWith(api, const TodayScreen()));
    await tester.pumpAndSettle();
    final button = find.byKey(const Key('switch.plug-turn_on'));
    await tester.ensureVisible(button);
    await tester.tap(button);
    await tester.tap(button);
    await tester.pump();
    expect(tapOf(tester, button), isNull);
    final container = ProviderScope.containerOf(tester.element(find.byType(TodayScreen)));
    final reloading = container.read(todayProvider.notifier).refresh();
    await tester.pump();
    refresh.complete(jsonResponse({}));
    await reloading;
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(tapOf(tester, button), isNull);
    expect(posts, 1);
    action.complete(jsonResponse({'detail': 'HA timeout'}, status: 409));
    await tester.pumpAndSettle();
    expect(find.textContaining('Aktion nicht bestätigt'), findsOneWidget);
    expect(posts, 1);
    await tester.tap(find.byTooltip('Haus aktualisieren'));
    await tester.pumpAndSettle();
    expect(tileWith('Steckdose', 'Aus'), findsOneWidget);
    expect(posts, 1);
  });

  testWidgets('dimmer previews locally and only sends once at release', (tester) async {
    await setScreenSize(tester, const Size(400, 1800));
    final backend = FakeBackend();
    addDefaults(backend);
    backend.json('GET', '/api/house/controls', {'status': 'ok', 'items': [
      {'entity_id': 'light.lamp', 'name': 'Lampe', 'state': 'on', 'actions': ['brightness'], 'brightness': 50},
      {'entity_id': 'switch.plug', 'name': 'Steckdose', 'state': 'off', 'actions': ['turn_on']},
    ]});
    backend.json('POST', '/api/house/actions', {'accepted': true});
    await tester.pumpWidget(appWith(backend.api(), const TodayScreen()));
    await tester.pumpAndSettle();
    final slider = find.byType(Slider);
    expect(slider, findsOneWidget);
    tester.widget<Slider>(slider).onChanged!(180);
    await tester.pump();
    expect(tester.widget<Slider>(slider).value, 180);
    expect(backend.sent('POST', '/api/house/actions'), isEmpty);
    tester.widget<Slider>(slider).onChangeEnd!(180);
    await tester.pumpAndSettle();
    expect(backend.sent('POST', '/api/house/actions'), hasLength(1));
    expect(bodyOf(backend.sent('POST', '/api/house/actions').single), {
      'entity_id': 'light.lamp', 'action': 'brightness', 'brightness': 180,
    });
  });


  for (final entity in ['script.evening', 'scene.evening']) {
    testWidgets('explicit activation for $entity sends no service data', (tester) async {
      await setScreenSize(tester, const Size(400, 1800));
      final backend = FakeBackend();
      addDefaults(backend);
      backend.json('GET', '/api/house/controls', {'status': 'ok', 'items': [
        {'entity_id': entity, 'name': 'Abend', 'state': 'off', 'actions': ['activate']},
      ]});
      backend.json('POST', '/api/house/actions', {'accepted': true});
      await tester.pumpWidget(appWith(backend.api(), const TodayScreen()));
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.byKey(Key('$entity-activate')));
      await tester.tap(find.byKey(Key('$entity-activate')));
      await tester.pumpAndSettle();
      expect(bodyOf(backend.sent('POST', '/api/house/actions').single), {'entity_id': entity, 'action': 'activate'});
    });
  }

  testWidgets('read only unknown states expose no actions or dimmer', (tester) async {
    await setScreenSize(tester, const Size(400, 1800));
    final backend = FakeBackend();
    addDefaults(backend);
    backend.json('GET', '/api/house/controls', {'status': 'unavailable', 'error': 'Nicht verfügbar', 'items': [
      {'entity_id': 'light.lamp', 'name': 'Lampe', 'state': null, 'actions': []},
      {'entity_id': 'switch.plug', 'name': 'Steckdose', 'state': 'on', 'actions': []},
    ]});
    await tester.pumpWidget(appWith(backend.api(), const TodayScreen()));
    await tester.pumpAndSettle();
    expect(tileWith('Lampe', 'Nicht verfügbar'), findsOneWidget);
    expect(tileWith('Steckdose', 'An'), findsOneWidget);
    expect(actionTiles, findsNothing);
    expect(find.byType(Slider), findsNothing);
  });

  testWidgets('offline remount cannot authorize using cached today fields', (tester) async {
    await setScreenSize(tester, const Size(400, 1800));
    final backend = FakeBackend();
    addDefaults(backend);
    backend.json('GET', '/api/today', {'house': {'status': 'ok', 'items': [
      {'entity_id': 'light.lamp', 'name': 'Lampe', 'state': 'on', 'actions': ['turn_off']},
    ]}});
    backend.json('GET', '/api/house/controls', {'status': 'ok', 'items': [
      {'entity_id': 'light.lamp', 'name': 'Lampe', 'state': 'on', 'actions': ['turn_off']},
    ]});
    final api = backend.api();
    await tester.pumpWidget(appWith(api, const TodayScreen()));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('light.lamp-turn_off')), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
    backend.offline = true;
    await tester.pumpWidget(appWith(api, const TodayScreen()));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('light.lamp-turn_off')), findsNothing);
    expect(find.byType(Slider), findsNothing);
    expect(tester.widget<Tooltip>(find.byKey(const Key('read-status'))).message, startsWith('Offline, Stand '));
  });

  testWidgets('controls network failure visible and refresh never replays a POST', (tester) async {
    await setScreenSize(tester, const Size(400, 1800));
    final backend = FakeBackend();
    addDefaults(backend);
    backend.json('GET', '/api/house/controls', {'detail': 'failure'}, status: 503);
    await tester.pumpWidget(appWith(backend.api(), const TodayScreen()));
    await tester.pumpAndSettle();
    expect(find.textContaining('Haussteuerung nicht verfügbar'), findsOneWidget);
    expect(actionTiles, findsNothing);
    backend.json('GET', '/api/house/controls', {'status': 'not_configured', 'items': []});
    await tester.ensureVisible(find.byTooltip('Haus aktualisieren'));
    await tester.tap(find.byTooltip('Haus aktualisieren'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('today-house')), findsNothing);
    expect(backend.sent('POST', '/api/house/actions'), isEmpty);
  });

  testWidgets('pending action survives card parity change during refresh', (tester) async {
  await setScreenSize(tester, const Size(1000, 1800));
  final action = Completer<http.Response>();
  var posts = 0;
  var reads = 0;
  final api = ApiClient(store: MemorySessionStore(url:'https://hub.test', access:'token'), httpClient: MockClient((r) async {
   if(r.url.path == '/api/auth/me') return jsonResponse(meJson);
   if(r.url.path == '/api/today') return jsonResponse(++reads == 1 ? {} : {'house': {'status':'ok','items':[]}});
   if(r.url.path == '/api/house/controls') return jsonResponse({'status':'ok','items':[{'entity_id':'script.evening','name':'Abend','state':'off','actions':['activate']}]});
   if(r.url.path == '/api/house/actions') {posts++; return action.future;}
   return jsonResponse({}, status:404);
  }));
  await tester.pumpWidget(appWith(api, const TodayScreen()));
  await tester.pumpAndSettle();
  final button = find.byKey(const Key('script.evening-activate'));
  await tester.ensureVisible(button);
  await tester.tap(button);
  await tester.pump();
  expect(posts, 1);
  final container = ProviderScope.containerOf(tester.element(find.byType(TodayScreen)));
  await container.read(todayProvider.notifier).refresh();
  await tester.pump();
  await tester.pump(const Duration(milliseconds:100));
  await tester.ensureVisible(button);
  final enabled = tapOf(tester, button) != null;
  if(enabled) await tester.tap(button);
  await tester.pump();
  debugPrint('INDEPENDENT_PROBE enabledWhilePending=$enabled posts=$posts');
  action.complete(jsonResponse({'detail':'timeout'},status:409));
  await tester.pumpAndSettle();
  expect(enabled, isFalse);
  expect(tapOf(tester, button), isNotNull);
  expect(posts, 1, reason:'refresh must not allow a second device action before the first resolves');
 });
  for (final status in [409, 200]) {
    testWidgets('activation outcome $status survives actual parity remount', (tester) async {
      await setScreenSize(tester, const Size(1000, 1800));
      final action = Completer<http.Response>();
      var posts = 0;
      var reads = 0;
      final api = ApiClient(
        store: MemorySessionStore(url: 'https://hub.test', access: 'token'),
        httpClient: MockClient((request) async {
          if (request.url.path == '/api/auth/me') return jsonResponse(meJson);
          if (request.url.path == '/api/today') {
            return jsonResponse(++reads == 1 ? {} : {'house': {'status': 'ok', 'items': []}});
          }
          if (request.url.path == '/api/house/controls') {
            return jsonResponse({'status': 'ok', 'items': [
              {'entity_id': 'script.evening', 'name': 'Abend', 'state': 'off', 'actions': ['activate']},
            ]});
          }
          if (request.url.path == '/api/house/actions') { posts++; return action.future; }
          return jsonResponse({}, status: 404);
        }),
      );
      await tester.pumpWidget(appWith(api, const TodayScreen()));
      await tester.pumpAndSettle();
      final button = find.byKey(const Key('script.evening-activate'));
      final oldState = tester.state(find.byType(HouseCard));
      await tester.ensureVisible(button);
      await tester.tap(button);
      await tester.pump();
      final container = ProviderScope.containerOf(tester.element(find.byType(TodayScreen)));
      await container.read(todayProvider.notifier).refresh();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      // Seit der Zusammenführung zu einer Haus-Karte verschiebt das Aktualisieren keine Karten mehr,
      // die Karte wird also nicht neu aufgebaut. Geprüft bleibt: Sperre, ein POST, sichtbarer Ausgang.
      expect(oldState.mounted, isTrue);
      expect(tapOf(tester, button), isNull);
      expect(posts, 1);
      action.complete(jsonResponse(status == 200
          ? {'accepted': true} : {'detail': 'HA timeout; outcome unknown'}, status: status));
      await tester.pumpAndSettle();
      final failure = find.textContaining('Aktion nicht bestätigt');
      debugPrint('REVIEW_PROBE status=$status posts=$posts enabled=${tapOf(tester, button) != null} errors=${failure.evaluate().length}');
      expect(failure, status == 409 ? findsOneWidget : findsNothing);
      // A later automatic read/remount must not acknowledge an unknown outcome.
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pumpWidget(appWith(api, const TodayScreen()));
      await tester.pumpAndSettle();
      expect(failure, status == 409 ? findsOneWidget : findsNothing);
      // Der Aktualisieren-Knopf erscheint nur bei einem Problem; die Karte aktualisiert sich sonst selbst.
      expect(find.byTooltip('Haus aktualisieren'), status == 409 ? findsOneWidget : findsNothing);
      if (status == 409) {
        await tester.ensureVisible(find.byTooltip('Haus aktualisieren'));
        await tester.tap(find.byTooltip('Haus aktualisieren'));
        await tester.pumpAndSettle();
      }
      expect(failure, findsNothing);
      expect(posts, 1);
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('stale session failure stays invisible while newer action remains locked', (tester) async {
    await setScreenSize(tester, const Size(1000, 1800));
    final oldReply = Completer<http.Response>();
    final newReply = Completer<http.Response>();
    var posts = 0;
    final api = ApiClient(
      store: MemorySessionStore(url: 'https://hub.test', access: 'token'),
      httpClient: MockClient((request) async {
        if (request.url.path == '/api/auth/me') return jsonResponse(meJson);
        if (request.url.path == '/api/auth/login') {
          return jsonResponse({'access_token': 'new-token', 'user': meJson});
        }
        if (request.url.path == '/api/house/controls') {
          return jsonResponse({'status': 'ok', 'items': [
            {'entity_id': 'script.evening', 'name': 'Abend', 'state': 'off', 'actions': ['activate']},
          ]});
        }
        if (request.url.path == '/api/house/actions') {
          return ++posts == 1 ? oldReply.future : newReply.future;
        }
        return jsonResponse({}, status: 404);
      }),
    );
    final button = find.byKey(const Key('script.evening-activate'));
    final failure = find.textContaining('Aktion nicht bestätigt');
    await tester.pumpWidget(appWith(api, const HouseCard(online: true)));
    await tester.pumpAndSettle();
    await tester.tap(button);
    await tester.pump();
    expect(posts, 1);
    await api.setServer('https://other.test');
    await api.login('alex', 'test-password');
    await tester.pumpWidget(appWith(api, const HouseCard(key: Key('new-session'), online: true)));
    await tester.pumpAndSettle();
    await tester.tap(button);
    await tester.pump();
    expect(posts, 2);
    oldReply.complete(jsonResponse({'detail': 'private old session failure'}, status: 409));
    // Do not settle the indeterminate indicator while the new POST is held.
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(failure, findsNothing);
    expect(find.textContaining('private'), findsNothing);
    expect(api.houseActionPending, isTrue);
    expect(tapOf(tester, button), isNull);
    newReply.complete(jsonResponse({'detail': 'private current session failure'}, status: 409));
    await tester.pumpAndSettle();
    expect(failure, findsOneWidget);
    expect(find.textContaining('private'), findsNothing);
    await api.setServer('https://third.test');
    await tester.pumpAndSettle();
    expect(failure, findsNothing);
    await api.login('alex', 'test-password');
    await tester.pumpWidget(appWith(api, const HouseCard(key: Key('third-session'), online: true)));
    await tester.pumpAndSettle();
    expect(failure, findsNothing);
    expect(posts, 2);
    expect(tester.takeException(), isNull);
  });

  for (final role in ['child', 'guest']) {
    testWidgets('canonical $role metadata remains read only in UI', (tester) async {
      await setScreenSize(tester, const Size(1000, 1800));
      final backend = FakeBackend();
      addDefaults(backend);
      backend.json('GET', '/api/auth/me', {...meJson, 'is_admin': false, 'role': role});
      backend.json('GET', '/api/house/controls', {'status': 'ok', 'items': [
        {'entity_id': 'light.lamp', 'name': 'Lampe', 'state': 'on', 'actions': [], 'brightness': 128},
        {'entity_id': 'script.evening', 'name': 'Abend', 'state': 'off', 'actions': []},
      ]});
      await tester.pumpWidget(appWith(backend.api(), const TodayScreen()));
      await tester.pumpAndSettle();
      expect(tileWith('Lampe', 'An'), findsOneWidget);
      expect(tileWith('Abend', 'Skript'), findsOneWidget);
      expect(actionTiles, findsNothing);
      expect(find.byType(Slider), findsNothing);
      expect(backend.sent('POST', '/api/house/actions'), isEmpty);
    });
  }

}
