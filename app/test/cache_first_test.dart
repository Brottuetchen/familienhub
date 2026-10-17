import 'dart:async';
import 'dart:convert';

import 'package:familienhub/models/task.dart';
import 'package:familienhub/services/api_exceptions.dart';

import 'package:familienhub/providers/providers.dart';
import 'package:familienhub/screens/main_shell.dart';
import 'package:familienhub/models/meals.dart';
import 'package:familienhub/screens/meals/meals_screen.dart';
import 'package:familienhub/screens/shopping/shopping_screen.dart';
import 'package:familienhub/screens/calendar/calendar_screen.dart';
import 'package:familienhub/screens/tasks/tasks_screen.dart';
import 'package:familienhub/screens/today/today_screen.dart';
import 'package:familienhub/services/api_client.dart';
import 'package:familienhub/services/session_store.dart';
import 'package:familienhub/widgets/common.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'helpers.dart';

Map<String, dynamic> todayJson(int count) => {
      'date': '2026-10-15',
      'events': [],
      'tasks': {'status': 'ok', 'items': []},
      'meals': [],
      'shopping_open': count,
      'reminders': [],
    };

Object pageJson(String path, String title,
        {String view = 'mine', String week = ''}) =>
    switch (path) {
      '/api/today' => {
          ...todayJson(3),
          'meals': [
            {'title': title, 'source': 'hub'}
          ]
        },
      '/api/tasks' => {
          'status': 'ok',
          'items': [
            {'uid': view, 'title': '$title-$view', 'done': false}
          ]
        },
      '/api/shopping' => {
          'status': 'ok',
          'groups': [
            {
              'key': 'manual',
              'items': [
                {'uid': 's1', 'summary': title, 'status': 'needs_action'}
              ]
            }
          ]
        },
      '/api/meals' => {
          'status': 'ok',
          'days': [
            {
              'date': '2026-10-15',
              'entries': [
                {'title': '$title-$week', 'source': 'hub'}
              ]
            }
          ]
        },
      '/api/calendar/events' => [
          {'title': title, 'start': '2026-10-15', 'all_day': true}
        ],
      '/api/auth/me' => meJson,
      '/api/auth/people' => [],
      _ => {'detail': 'Not Found'},
    };

void main() {
  setUp(setUpTestEnv);

  testWidgets(
      'persisted today renders before blocked HTTP and refreshes in place',
      (tester) async {
    await setScreenSize(tester, const Size(400, 1400));
    final store = MemorySessionStore(
        url: 'https://hub.test', access: 'token', refresh: 'refresh');
    final seed = ApiClient(
        store: store,
        httpClient: MockClient((_) async => jsonResponse(todayJson(3))));
    await seed.today();
    final pending = Completer<http.Response>();
    final api = ApiClient(
        store: store,
        httpClient: MockClient((r) async {
          if (r.url.path == '/api/today') return pending.future;
          if (r.url.path == '/api/auth/me') return jsonResponse(meJson);
          return jsonResponse({'detail': 'Not found'}, status: 404);
        }));
    await tester.pumpWidget(appWith(api, const TodayScreen()));
    await tester.pump();
    await tester.pump();
    expect(find.text('3 Artikel offen'), findsOneWidget);
    expect(find.byType(HubLoader), findsNothing);
    expect(tester.widget<Tooltip>(find.byKey(const Key('read-status'))).message, contains('Stand '));
    expect(find.textContaining('Offline'), findsNothing);
    pending.complete(jsonResponse(todayJson(4)));
    await tester.pumpAndSettle();
    expect(find.text('4 Artikel offen'), findsOneWidget);
    expect(find.text('3 Artikel offen'), findsNothing);
  });

  test('identical concurrent HTTP reads share one request', () async {
    final pending = Completer<http.Response>();
    var requests = 0;
    final api = ApiClient(
      store: MemorySessionStore(url: 'https://hub.test', access: 'token'),
      httpClient: MockClient((_) {
        requests++;
        return pending.future;
      }),
    );
    final first = api.today();
    final second = api.today();
    await Future<void>.delayed(Duration.zero);
    expect(requests, 1);
    pending.complete(jsonResponse(todayJson(3)));
    await Future.wait([first, second]);
  });

  test('cache is isolated by server and login session', () async {
    final store =
        MemorySessionStore(url: 'https://one.test', access: 'a', refresh: 'r');
    final api = ApiClient(
        store: store,
        httpClient: MockClient((_) async => jsonResponse(todayJson(3))));
    await api.today();
    expect(await api.cached('today', (j) => j), isNotNull);
    store.url = 'https://two.test';
    expect(await api.cached('today', (j) => j), isNull);
    store.url = 'https://one.test';
    store.access = 'b';
    store.refresh = 'other-session';
    expect(await api.cached('today', (j) => j), isNull);
  });

  test('logout clears kept providers and rejects late old HTTP', () async {
    final store =
        MemorySessionStore(url: 'https://hub.test', access: 'a', refresh: 'r');
    final pending = Completer<http.Response>();
    var block = false;
    final api = ApiClient(
        store: store,
        httpClient: MockClient((r) async {
          if (r.url.path == '/api/auth/logout') return jsonResponse(null);
          return block ? pending.future : jsonResponse(todayJson(3));
        }));
    final container = ProviderContainer(
        overrides: [apiClientProvider.overrideWithValue(api)]);
    addTearDown(container.dispose);
    await container.read(todayProvider.notifier).ready;
    block = true;
    final old = api.today();
    final rejected = expectLater(old, throwsA(isA<UnauthorizedException>()));
    await Future<void>.delayed(Duration.zero);
    await api.logout();
    expect(container.read(todayProvider).valueOrNull, isNull);
    pending.complete(jsonResponse(todayJson(99)));
    await rejected;
    expect(container.read(todayProvider).valueOrNull, isNull);
    expect(await api.cached('today', (j) => j), isNull);
  });

  test('server selection clears credentials and kept content', () async {
    final backend = FakeBackend();
    addDefaults(backend);
    final store =
        MemorySessionStore(url: 'https://old.test', access: 'a', refresh: 'r');
    final api = backend.api(store: store);
    final container = ProviderContainer(
        overrides: [apiClientProvider.overrideWithValue(api)]);
    addTearDown(container.dispose);
    await container.read(todayProvider.notifier).ready;
    final session = SessionNotifier(api, autoStart: false);
    addTearDown(session.dispose);
    await session.setServer('https://new.test');
    expect(store.access, isNull);
    expect(store.refresh, isNull);
    expect(container.read(todayProvider).valueOrNull, isNull);
    expect(await api.cached('today', (j) => j), isNull);
  });

  test('expired access token cannot render persisted cache while offline',
      () async {
    final payload = base64Url
        .encode(utf8.encode(jsonEncode({'sub': '1', 'exp': 1})))
        .replaceAll('=', '');
    final store = MemorySessionStore(
        url: 'https://hub.test',
        access: 'e30.$payload.signature',
        refresh: 'r');
    final api = ApiClient(
        store: store,
        httpClient: MockClient((_) async => jsonResponse(todayJson(3))));
    await api.today();
    expect(await api.cached('today', (j) => j), isNull);
    final offline = ApiClient(
        store: store,
        httpClient:
            MockClient((_) async => throw http.ClientException('offline')));
    await expectLater(offline.today(), throwsA(isA<UnauthorizedException>()));
  });

  testWidgets('forbidden refresh removes cached content and is not offline',
      (tester) async {
    await setScreenSize(tester, const Size(400, 1400));
    var forbidden = false;
    final api = ApiClient(
        store: MemorySessionStore(url: 'https://hub.test', access: 'a'),
        httpClient: MockClient((r) async {
          if (r.url.path == '/api/auth/me') return jsonResponse(meJson);
          if (r.url.path == '/api/today') {
            return forbidden
                ? jsonResponse({'detail': 'Kein Zugriff'}, status: 403)
                : jsonResponse(todayJson(3));
          }
          return jsonResponse({}, status: 404);
        }));
    await api.today();
    forbidden = true;
    await tester.pumpWidget(appWith(api, const TodayScreen()));
    await tester.pumpAndSettle();
    expect(find.text('3 Artikel offen'), findsNothing);
    expect(find.text('Kein Zugriff'), findsOneWidget);
    expect(find.textContaining('Offline'), findsNothing);
    expect(await api.cached('today', (j) => j), isNull);
  });

  test('successful task mutation invalidates every view and today only',
      () async {
    var count = 3;
    final api = ApiClient(
        store: MemorySessionStore(url: 'https://hub.test', access: 'a'),
        httpClient: MockClient((r) async {
          if (r.method == 'POST') {
            count = 4;
            return jsonResponse({});
          }
          if (r.url.path == '/api/tasks') {
            return jsonResponse({'status': 'ok', 'items': []});
          }
          if (r.url.path == '/api/shopping') {
            return jsonResponse({'status': 'ok', 'groups': []});
          }
          return jsonResponse(todayJson(count));
        }));
    final container = ProviderContainer(
        overrides: [apiClientProvider.overrideWithValue(api)]);
    addTearDown(container.dispose);
    await container.read(todayProvider.notifier).ready;
    for (final view in TaskView.values) {
      await api.tasks(view);
    }
    await api.shopping();
    await api.completeTask('t1');
    for (final view in TaskView.values) {
      expect(await api.cached('tasks:${view.apiName}', (j) => j), isNull);
    }
    expect(await api.cached('shopping', (j) => j), isNotNull);
    await Future<void>.delayed(Duration.zero);
    await Future<void>.delayed(Duration.zero);
    expect(container.read(todayProvider).requireValue.data.shoppingOpen, 4);
  });

  test('calendar cache separates requested day windows', () async {
    final api = ApiClient(
        store: MemorySessionStore(url: 'https://hub.test', access: 'a'),
        httpClient: MockClient((r) async => jsonResponse([
              {'title': r.url.queryParameters['days'], 'all_day': true}
            ])));
    await api.events(days: 14);
    await api.events(days: 30);
    final offline = ApiClient(
        store: api.store,
        httpClient:
            MockClient((_) async => throw http.ClientException('offline')));
    expect((await offline.events(days: 14)).data.single.title, '14');
    expect((await offline.events(days: 30)).data.single.title, '30');
  });

  for (final (path, screen) in <(String, Widget)>[
    ('/api/today', const TodayScreen()),
    ('/api/tasks', const TasksScreen()),
    ('/api/shopping', const ShoppingScreen()),
    ('/api/meals', const MealsScreen()),
    ('/api/calendar/events', const CalendarScreen()),
  ]) {
    testWidgets(
        '$path persisted content and explicit refresh keep content while HTTP waits',
        (tester) async {
      await setScreenSize(tester, const Size(400, 1400));
      final store = MemorySessionStore(
          url: 'https://hub.test', access: 'a', refresh: 'r');
      final seed = ApiClient(
          store: store,
          httpClient: MockClient((r) async => jsonResponse(pageJson(
              r.url.path, 'Alt',
              view: r.url.queryParameters['view'] ?? 'mine',
              week: r.url.queryParameters['week'] ?? ''))));
      switch (path) {
        case '/api/today':
          await seed.today();
        case '/api/tasks':
          await seed.tasks(TaskView.mine);
        case '/api/shopping':
          await seed.shopping();
        case '/api/meals':
          await seed.meals(isoWeekOf(DateTime.now()));
        default:
          await seed.events(days: 30);
      }
      var pending = Completer<http.Response>();
      var requests = 0;
      final api = ApiClient(
          store: store,
          httpClient: MockClient((r) async {
            if (r.url.path == path) {
              requests++;
              return pending.future;
            }
            return jsonResponse(pageJson(r.url.path, 'Andere'),
                status: r.url.path == '/api/modules' ? 404 : 200);
          }));
      await tester.pumpWidget(appWith(api, screen));
      await tester.pump();
      await tester.pump();
      expect(find.textContaining('Alt'), findsOneWidget);
      expect(find.byType(HubLoader), findsNothing);
      pending.complete(jsonResponse(pageJson(path, 'Neu')));
      await tester.pumpAndSettle();
      expect(find.textContaining('Neu'), findsOneWidget);
      pending = Completer<http.Response>();
      var completed = false;
      final refresh = tester
          .widget<RefreshIndicator>(find.byType(RefreshIndicator).first)
          .onRefresh()
          .then((_) => completed = true);
      await tester.pump();
      expect(requests, 2);
      expect(completed, isFalse);
      expect(find.textContaining('Neu'), findsOneWidget);
      // Einzige Ladeanzeige ist die des Herunterziehens (oben), keine ganzseitige
      expect(find.byType(HubLoader), findsOneWidget);
      expect(find.byKey(const Key('pull-refresh-loader')), findsOneWidget);
      pending.complete(jsonResponse(pageJson(path, 'Frisch')));
      await refresh;
      await tester.pumpAndSettle();
      expect(find.textContaining('Frisch'), findsOneWidget);
    });
  }

  testWidgets(
      'main tab returns show content immediately and revalidate in background',
      (tester) async {
    await setScreenSize(tester, const Size(400, 1400));
    final pending = <String, Completer<http.Response>>{};
    final requests = <String, int>{};
    final api = ApiClient(
        store: MemorySessionStore(url: 'https://hub.test', access: 'a'),
        httpClient: MockClient((r) async {
          final path = r.url.path;
          requests[path] = (requests[path] ?? 0) + 1;
          if (pending[path] case final p?) return p.future;
          return jsonResponse(
              pageJson(path, path,
                  view: r.url.queryParameters['view'] ?? 'mine',
                  week: r.url.queryParameters['week'] ?? ''),
              status: path == '/api/modules' ? 404 : 200);
        }));
    await tester.pumpWidget(appWith(api, const MainShell(startPush: false)));
    await tester.pumpAndSettle();
    final destinations = [
      ('Termine', '/api/calendar/events'),
      ('Aufgaben', '/api/tasks'),
      ('Einkauf', '/api/shopping'),
      ('Essen', '/api/meals')
    ];
    for (final (label, path) in destinations) {
      await tester.tap(find.widgetWithText(NavigationDestination, label));
      await tester.pumpAndSettle();
      expect(find.textContaining(path), findsOneWidget);
    }
    for (final (label, path) in [('Heute', '/api/today'), ...destinations]) {
      final before = requests[path]!;
      pending[path] = Completer<http.Response>();
      await tester.tap(find.widgetWithText(NavigationDestination, label));
      await tester.pump();
      expect(find.textContaining(path), findsOneWidget);
      expect(find.byType(HubLoader), findsNothing);
      await tester.pump();
      expect(requests[path], before + 1);
      pending[path]!.complete(jsonResponse(pageJson(path, path)));
      await tester.pumpAndSettle();
      pending.remove(path);
    }
  });

  test('401 with unreachable refresh never falls back to cached data',
      () async {
    var reject = false;
    final api = ApiClient(
        store: MemorySessionStore(
            url: 'https://hub.test', access: 'a', refresh: 'r'),
        httpClient: MockClient((r) async {
          if (r.url.path == '/api/auth/refresh') {
            throw http.ClientException('offline');
          }
          return reject
              ? jsonResponse({'detail': 'expired'}, status: 401)
              : jsonResponse(todayJson(3));
        }));
    await api.today();
    reject = true;
    await expectLater(api.today(), throwsA(isA<UnauthorizedException>()));
    expect(await api.cached('today', (j) => j), isNull);
  });

  test('late pre-mutation read cannot replace or erase refreshed content',
      () async {
    final pending = Completer<http.Response>();
    var gets = 0;
    final api = ApiClient(
        store: MemorySessionStore(url: 'https://hub.test', access: 'a'),
        httpClient: MockClient((r) async {
          if (r.method == 'POST') return jsonResponse({});
          gets++;
          if (gets == 2) return pending.future;
          return jsonResponse(todayJson(gets == 1 ? 3 : 4));
        }));
    final container = ProviderContainer(
        overrides: [apiClientProvider.overrideWithValue(api)]);
    addTearDown(container.dispose);
    final read = container.read(todayProvider.notifier);
    await read.ready;
    final old = read.refresh();
    final rejected = expectLater(old, throwsA(isA<Exception>()));
    await Future<void>.delayed(Duration.zero);
    await api.completeTask('t1');
    await Future<void>.delayed(Duration.zero);
    await Future<void>.delayed(Duration.zero);
    expect(container.read(todayProvider).requireValue.data.shoppingOpen, 4);
    pending.complete(jsonResponse(todayJson(99)));
    await rejected;
    expect(container.read(todayProvider).requireValue.data.shoppingOpen, 4);
  });

  test('late token refresh after new login cannot restore the old session',
      () async {
    final refresh = Completer<http.Response>();
    final refreshStarted = Completer<void>();
    final store = MemorySessionStore(
        url: 'https://hub.test', access: 'old', refresh: 'old-refresh');
    final api = ApiClient(
        store: store,
        httpClient: MockClient((r) async {
          if (r.url.path == '/api/auth/login') {
            return jsonResponse({
              'access_token': 'new',
              'refresh_token': 'new-refresh',
              'user': meJson
            });
          }
          if (r.url.path == '/api/auth/refresh') {
            refreshStarted.complete();
            return refresh.future;
          }
          if (r.headers['Authorization'] == 'Bearer old') {
            return jsonResponse({}, status: 401);
          }
          return jsonResponse(todayJson(4));
        }));
    final old = api.today();
    final rejected = expectLater(old, throwsA(isA<UnauthorizedException>()));
    await refreshStarted.future;
    await api.login('new-user', 'password');
    await api.today();
    refresh.complete(jsonResponse({
      'access_token': 'restored-old',
      'refresh_token': 'restored-old-refresh'
    }));
    await rejected;
    expect(store.access, 'new');
    expect(store.refresh, 'new-refresh');
    expect((await api.cached('today', (j) => j))?.data['shopping_open'], 4);
  });

  testWidgets(
      'task mutation keeps unrelated loaded tasks visible during revalidation',
      (tester) async {
    final pending = Completer<http.Response>();
    var completed = false;
    final api = ApiClient(
        store: MemorySessionStore(url: 'https://hub.test', access: 'a'),
        httpClient: MockClient((r) async {
          if (r.method == 'POST') {
            completed = true;
            return jsonResponse({});
          }
          if (r.url.path == '/api/tasks') {
            if (completed) return pending.future;
            return jsonResponse({
              'status': 'ok',
              'items': [
                {'uid': 'first', 'title': 'Erledigen', 'done': false},
                {'uid': 'other', 'title': 'Behalten', 'done': false},
              ]
            });
          }
          return jsonResponse(pageJson(r.url.path, 'Andere'),
              status: r.url.path == '/api/modules' ? 404 : 200);
        }));
    await tester.pumpWidget(appWith(api, const TasksScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(Checkbox).first);
    await tester.pump();
    await tester.pump();
    expect(find.text('Behalten'), findsOneWidget);
    expect(find.byType(HubLoader), findsNothing);
    pending.complete(jsonResponse({
      'status': 'ok',
      'items': [
        {'uid': 'other', 'title': 'Behalten', 'done': false}
      ]
    }));
    await tester.pumpAndSettle();
  });

  testWidgets(
      'kept page content expires with the access token even if HTTP blocks',
      (tester) async {
    await setScreenSize(tester, const Size(400, 1400));
    final exp = DateTime.now().millisecondsSinceEpoch ~/ 1000 + 10;
    final payload = base64Url
        .encode(utf8.encode(jsonEncode({'sub': '1', 'exp': exp})))
        .replaceAll('=', '');
    var blocked = false;
    final pending = Completer<http.Response>();
    final api = ApiClient(
        store: MemorySessionStore(
            url: 'https://hub.test',
            access: 'e30.$payload.signature',
            refresh: 'r'),
        httpClient: MockClient((r) async {
          if (r.url.path == '/api/auth/me') return jsonResponse(meJson);
          if (r.url.path == '/api/today') {
            return blocked ? pending.future : jsonResponse(todayJson(3));
          }
          return jsonResponse({}, status: 404);
        }));
    await tester.pumpWidget(appWith(api, const TodayScreen()));
    await tester.pumpAndSettle();
    expect(find.text('3 Artikel offen'), findsOneWidget);
    blocked = true;
    await tester.pump(const Duration(seconds: 11));
    expect(find.text('3 Artikel offen'), findsNothing);
    pending.complete(jsonResponse({}, status: 401));
    await tester.pumpAndSettle();
  });

  test('loaded today survives the last listener leaving', () async {
    final backend = FakeBackend();
    addDefaults(backend);
    final container = ProviderContainer(
        overrides: [apiClientProvider.overrideWithValue(backend.api())]);
    addTearDown(container.dispose);
    final sub = container.listen(todayProvider, (_, __) {});
    await container.read(todayProvider.notifier).ready;
    sub.close();
    await container.pump();
    expect(container.read(todayProvider).hasValue, isTrue);
  });
}
