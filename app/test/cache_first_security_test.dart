import 'dart:async';
import 'dart:convert';
import 'package:familienhub/services/api_client.dart';
import 'package:familienhub/services/session_store.dart';
import 'package:familienhub/services/cache.dart';
import 'package:familienhub/services/api_exceptions.dart';
import 'package:familienhub/screens/tasks/tasks_screen.dart';
import 'package:familienhub/widgets/common.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:familienhub/providers/providers.dart';
import 'package:familienhub/models/task.dart';
import 'package:familienhub/models/meals.dart';
import 'package:familienhub/screens/meals/meals_screen.dart';
import 'package:familienhub/screens/shopping/shopping_screen.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'helpers.dart';

String jwt(String sub, int exp) =>
    'e30.${base64Url.encode(utf8.encode(jsonEncode({
              'sub': sub,
              'exp': exp
            }))).replaceAll('=', '')}.sig';

class DelayedWriteStore extends MemorySessionStore {
  final started = Completer<void>();
  final release = Completer<void>();
  DelayedWriteStore()
      : super(url: 'https://old.test', access: 'old', refresh: 'old-refresh');
  @override
  Future<void> saveTokens({required String access, String? refresh}) async {
    if (access != 'rotated-old') {
      return super.saveTokens(access: access, refresh: refresh);
    }
    this.access = access;
    started.complete();
    await release.future;
    this.refresh = refresh;
  }
}

class DelayedReadStore extends MemorySessionStore {
  final started = Completer<void>();
  final release = Completer<void>();
  bool block = true;
  DelayedReadStore()
      : super(
            url: 'https://old.test',
            access: jwt('1', 4102444800),
            refresh: 'old-refresh');
  @override
  Future<String?> refreshToken() async {
    final value = refresh;
    if (block) {
      block = false;
      started.complete();
      await release.future;
    }
    return value;
  }
}

class PausedRemoval extends ResponseCache {
  bool pause = false;
  final started = Completer<void>();
  final release = Completer<void>();
  @override
  Future<void> removeWhere(bool Function(String) matches) async {
    if (pause) {
      pause = false;
      started.complete();
      await release.future;
    }
    await super.removeWhere(matches);
  }
}

void main() {
  setUp(setUpTestEnv);

  test('old denied cache removal cannot clear a newly logged-in provider', () async {
    final cache = PausedRemoval();
    var deny = false;
    final api = ApiClient(
      store: MemorySessionStore(url: 'https://hub.test', access: 'old', refresh: 'old-r'),
      cache: cache,
      httpClient: MockClient((r) async {
        if (r.url.path == '/api/auth/login') {
          return jsonResponse({'access_token': 'new', 'refresh_token': 'new-r', 'user': meJson});
        }
        if (deny) return jsonResponse({'detail': 'old session denied'}, status: 403);
        return jsonResponse({'date': '2026-10-16', 'tasks': {'items': []}, 'shopping_open': 7});
      }),
    );
    final container = ProviderContainer(overrides: [apiClientProvider.overrideWithValue(api)]);
    addTearDown(container.dispose);
    final read = container.read(todayProvider.notifier);
    await read.ready;
    cache.pause = true;
    deny = true;
    final rejected = expectLater(read.refresh(), throwsA(isA<ApiException>()));
    await cache.started.future;
    deny = false;
    await api.login('new-user', 'password');
    await read.refresh();
    expect(container.read(todayProvider).valueOrNull?.data.shoppingOpen, 7);
    cache.release.complete();
    await rejected;
    expect(container.read(todayProvider).valueOrNull?.data.shoppingOpen, 7);
  });
  test('review: token persistence completing after login stays in new session',
      () async {
    final store = DelayedWriteStore();
    final api = ApiClient(
        store: store,
        httpClient: MockClient((r) async {
          if (r.url.path == '/api/auth/refresh') {
            return jsonResponse({
              'access_token': 'rotated-old',
              'refresh_token': 'rotated-old-refresh'
            });
          }
          if (r.url.path == '/api/auth/login') {
            return jsonResponse({
              'access_token': 'new',
              'refresh_token': 'new-refresh',
              'user': meJson
            });
          }
          if (r.headers['Authorization'] == 'Bearer old') {
            return jsonResponse({}, status: 401);
          }
          return jsonResponse({
            'date': '2026-10-16',
            'tasks': {'items': []},
            'shopping_open': 4
          });
        }));
    final old = api.today();
    final rejected = expectLater(old, throwsA(isA<UnauthorizedException>()));
    await store.started.future;
    final login = api.login('new-user', 'test-password');
    // Let login reach persistence while the old split write is suspended.
    await Future<void>.delayed(Duration.zero);
    store.release.complete();
    await login;
    await rejected;
    expect(store.access, 'new');
    expect(store.refresh, 'new-refresh',
        reason: 'Old async persistence must not replace new refresh token');
  });

  test(
      'review: a delayed refresh-token read cannot send old refresh to new server',
      () async {
    final store = DelayedReadStore();
    var sentOldRefreshToNewServer = false;
    final api = ApiClient(
        store: store,
        httpClient: MockClient((r) async {
          if (r.url.path == '/api/auth/refresh') {
            sentOldRefreshToNewServer = r.url.host == 'new.test' &&
                bodyOf(r)['refresh_token'] == 'old-refresh';
            return jsonResponse({}, status: 401);
          }
          if (r.url.path == '/api/auth/login') {
            return jsonResponse({
              'access_token': jwt('2', 4102444800),
              'refresh_token': 'new-refresh',
              'user': meJson
            });
          }
          return jsonResponse({}, status: 401);
        }));
    final old = api.today();
    final rejected = expectLater(old, throwsA(isA<UnauthorizedException>()));
    await store.started.future;
    await api.setServer('https://new.test');
    await api.login('new-user', 'test-password');
    store.release.complete();
    await rejected;
    expect(sentOldRefreshToNewServer, isFalse,
        reason: 'Refresh credential must stay bound to original server/epoch');
  });

  testWidgets('review: task detail clears at local token expiry',
      (tester) async {
    await setScreenSize(tester, const Size(1000, 1000));
    final exp = DateTime.now().millisecondsSinceEpoch ~/ 1000 + 10;
    final store = MemorySessionStore(
        url: 'https://hub.test', access: jwt('1', exp), refresh: 'r');
    var block = false;
    final pending = Completer<http.Response>();
    final api = ApiClient(
        store: store,
        httpClient: MockClient((r) async {
          if (r.url.path == '/api/auth/me') return jsonResponse(meJson);
          if (r.url.path == '/api/auth/people') return jsonResponse([]);
          if (r.url.path == '/api/tasks') {
            return block
                ? pending.future
                : jsonResponse({
                    'status': 'ok',
                    'items': [
                      {
                        'uid': 'sensitive',
                        'title': 'Private task',
                        'notes': 'Private notes',
                        'done': false
                      }
                    ]
                  });
          }
          return jsonResponse({}, status: 404);
        }));
    await tester.pumpWidget(appWith(api, const TasksScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Private task'));
    await tester.pumpAndSettle();
    expect(find.text('Private notes'), findsOneWidget);
    block = true;
    await tester.pump(const Duration(seconds: 11));
    final notesStillVisible = find.text('Private notes').evaluate().length;
    pending.complete(jsonResponse({}, status: 401));
    await tester.pumpAndSettle();
    expect(notesStillVisible, 0,
        reason: 'Detail pane retains protected task after provider expiry');
  });

  test('secure platform split writes cannot mix refresh and login credentials',
      () async {
    SharedPreferences.setMockInitialValues(
        {'server_base_url': 'https://old.test'});
    final values = <String, String>{
      'access_token': 'old',
      'refresh_token': 'old-refresh'
    };
    final started = Completer<void>();
    final release = Completer<void>();
    const channel =
        MethodChannel('plugins.it_nomads.com/flutter_secure_storage');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
      final args = call.arguments as Map;
      final key = args['key'] as String;
      switch (call.method) {
        case 'read':
          return values[key];
        case 'delete':
          values.remove(key);
          return null;
        case 'write':
          final value = args['value'] as String;
          if (key == 'refresh_token' && value == 'rotated-old-refresh') {
            started.complete();
            await release.future;
          }
          values[key] = value;
          return null;
      }
      throw StateError('Unexpected platform call ${call.method}');
    });
    addTearDown(() => TestDefaultBinaryMessengerBinding
        .instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null));
    final store = SecureSessionStore();
    final api = ApiClient(
        store: store,
        httpClient: MockClient((r) async {
          if (r.url.path == '/api/auth/refresh') {
            return jsonResponse({
              'access_token': 'rotated-old',
              'refresh_token': 'rotated-old-refresh'
            });
          }
          if (r.url.path == '/api/auth/login') {
            return jsonResponse({
              'access_token': 'new',
              'refresh_token': 'new-refresh',
              'user': meJson
            });
          }
          return jsonResponse({}, status: 401);
        }));
    final rejected =
        expectLater(api.today(), throwsA(isA<UnauthorizedException>()));
    await started.future;
    final login = api.login('new-user', 'password');
    await Future<void>.delayed(Duration.zero);
    release.complete();
    await login;
    await rejected;
    expect(await store.accessToken(), 'new');
    expect(await store.refreshToken(), 'new-refresh');
  });

  for (final wide in [true, false]) {
    for (final denied in [false, true]) {
      testWidgets(
          'task ${wide ? 'pane' : 'modal'} clears on ${denied ? '403' : 'expiry'}',
          (tester) async {
        await setScreenSize(tester, Size(wide ? 1000 : 400, 1000));
        final exp = DateTime.now().millisecondsSinceEpoch ~/ 1000 + 10;
        final pending = Completer<http.Response>();
        var block = false;
        final api = ApiClient(
          store: MemorySessionStore(
              url: 'https://hub.test', access: jwt('1', exp)),
          httpClient: MockClient((r) async {
            if (r.url.path == '/api/auth/me') return jsonResponse(meJson);
            if (r.url.path == '/api/auth/people') return jsonResponse([]);
            if (r.url.path == '/api/tasks') {
              return block
                  ? pending.future
                  : jsonResponse({
                      'status': 'ok',
                      'items': [
                        {
                          'uid': 'private',
                          'title': 'Private task',
                          'notes': 'Private notes',
                          'done': false
                        }
                      ]
                    });
            }
            return jsonResponse({}, status: 404);
          }),
        );
        final container = ProviderContainer(
            overrides: [apiClientProvider.overrideWithValue(api)]);
        await tester.pumpWidget(UncontrolledProviderScope(
            container: container,
            child: const MaterialApp(home: TasksScreen())));
        await tester.pumpAndSettle();
        await tester.tap(find.text('Private task'));
        await tester.pumpAndSettle();
        expect(find.text('Private notes'), findsOneWidget);
        block = true;
        if (denied) {
          final refresh =
              container.read(tasksProvider(TaskView.mine).notifier).refresh();
          final rejected = expectLater(refresh, throwsA(isA<ApiException>()));
          await tester.pump();
          pending
              .complete(jsonResponse({'detail': 'Kein Zugriff'}, status: 403));
          await rejected;
          await tester.pumpAndSettle();
        } else {
          await tester.pump(const Duration(seconds: 11));
          expect(find.text('Private notes'), findsNothing);
          pending.complete(jsonResponse({}, status: 401));
          await tester.pumpAndSettle();
        }
        expect(find.text('Private notes'), findsNothing);
        await tester.pumpWidget(const SizedBox.shrink());
        container.dispose();
      });
    }
  }

  testWidgets('task delete confirmation clears captured title on denial',
      (tester) async {
    final backend = FakeBackend();
    addDefaults(backend);
    backend.json('GET', '/api/tasks', {
      'status': 'ok',
      'items': [
        {'uid': 'secret', 'title': 'Secret title', 'done': false}
      ]
    });
    final api = backend.api();
    final container = ProviderContainer(
        overrides: [apiClientProvider.overrideWithValue(api)]);
    addTearDown(container.dispose);
    await tester.pumpWidget(UncontrolledProviderScope(
        container: container, child: const MaterialApp(home: TasksScreen())));
    await tester.pumpAndSettle();
    await tester.drag(
        find.byType(Dismissible), const Offset(-600, 0));
    await tester.pumpAndSettle();
    expect(find.textContaining('„Secret title“'), findsOneWidget);
    backend.json('GET', '/api/tasks', {'detail': 'Kein Zugriff'}, status: 403);
    await expectLater(
        container.read(tasksProvider(TaskView.mine).notifier).refresh(),
        throwsA(isA<ApiException>()));
    await tester.pumpAndSettle();
    expect(find.textContaining('Secret title'), findsNothing);
    expect(backend.sent('DELETE', '/api/tasks/secret'), isEmpty);
  });

  testWidgets('meal delete confirmation clears captured entry on denial',
      (tester) async {
    final backend = FakeBackend();
    addDefaults(backend);
    backend.json('GET', '/api/meals', {
      'status': 'ok',
      'days': [
        {
          'date': '2026-10-16',
          'entries': [
            {'id': 7, 'title': 'Secret meal', 'source': 'hub'}
          ]
        }
      ]
    });
    final container = ProviderContainer(
        overrides: [apiClientProvider.overrideWithValue(backend.api())]);
    addTearDown(container.dispose);
    await tester.pumpWidget(UncontrolledProviderScope(
        container: container, child: const MaterialApp(home: MealsScreen())));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Löschen'));
    await tester.pumpAndSettle();
    expect(find.textContaining('„Secret meal“'), findsOneWidget);
    backend.json('GET', '/api/meals', {'detail': 'Kein Zugriff'}, status: 403);
    await expectLater(
        container
            .read(mealsProvider(isoWeekOf(DateTime.now())).notifier)
            .refresh(),
        throwsA(isA<ApiException>()));
    await tester.pumpAndSettle();
    expect(find.textContaining('Secret meal'), findsNothing);
    expect(backend.sent('DELETE', '/api/meals/7'), isEmpty);
  });

  testWidgets('task view return keeps its own content while HTTP blocks',
      (tester) async {
    await setScreenSize(tester, const Size(1000, 1000));
    final pending = Completer<http.Response>();
    var block = false;
    var mineReads = 0;
    final api = ApiClient(
        store: MemorySessionStore(url: 'https://hub.test', access: 'a'),
        httpClient: MockClient((r) async {
          if (r.url.path == '/api/auth/people') return jsonResponse([]);
          if (r.url.path == '/api/tasks') {
            final view = r.url.queryParameters['view']!;
            if (view == 'mine') {
              mineReads++;
              if (block) return pending.future;
            }
            return jsonResponse({
              'status': 'ok',
              'items': [
                {'uid': view, 'title': 'Task-$view', 'done': false}
              ]
            });
          }
          return jsonResponse(meJson);
        }));
    await tester.pumpWidget(appWith(api, const TasksScreen()));
    await tester.pumpAndSettle();
    expect(find.text('Task-mine'), findsOneWidget);
    await tester.tap(find.text(TaskView.family.label));
    await tester.pumpAndSettle();
    expect(find.text('Task-family'), findsOneWidget);
    final before = mineReads;
    block = true;
    await tester.tap(find.text(TaskView.mine.label));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.text('Task-mine'), findsOneWidget);
    expect(find.text('Task-family'), findsNothing);
    expect(find.byType(HubLoader), findsNothing);
    expect(mineReads, before + 1);
    pending.complete(jsonResponse({
      'status': 'ok',
      'items': [
        {'uid': 'mine', 'title': 'Fresh-mine', 'done': false}
      ]
    }));
    await tester.pumpAndSettle();
    expect(find.text('Fresh-mine'), findsOneWidget);
  });

  testWidgets('meal week return keeps the correct week while HTTP blocks',
      (tester) async {
    final current = isoWeekOf(DateTime.now());
    final next = isoWeekOf(DateTime.now().add(const Duration(days: 7)));
    final pending = Completer<http.Response>();
    var block = false;
    var currentReads = 0;
    Object meals(String title) => {
          'status': 'ok',
          'days': [
            {
              'date': '2026-10-16',
              'entries': [
                {'title': title, 'source': 'hub'}
              ]
            }
          ]
        };
    final api = ApiClient(
        store: MemorySessionStore(url: 'https://hub.test', access: 'a'),
        httpClient: MockClient((r) async {
          final week = r.url.queryParameters['week']!;
          if (week == current) {
            currentReads++;
            if (block) return pending.future;
          }
          return jsonResponse(meals('Meal-$week'));
        }));
    await tester.pumpWidget(appWith(api, const MealsScreen()));
    await tester.pumpAndSettle();
    expect(find.text('Meal-$current'), findsOneWidget);
    await tester.tap(find.byTooltip('Nächste Woche'));
    await tester.pumpAndSettle();
    expect(find.text('Meal-$next'), findsOneWidget);
    final before = currentReads;
    block = true;
    await tester.tap(find.byTooltip('Vorige Woche'));
    await tester.pump();
    expect(find.text('Meal-$current'), findsOneWidget);
    expect(find.text('Meal-$next'), findsNothing);
    expect(find.byType(HubLoader), findsNothing);
    await tester.pump();
    expect(currentReads, before + 1);
    pending.complete(jsonResponse(meals('Fresh-$current')));
    await tester.pumpAndSettle();
    expect(find.text('Fresh-$current'), findsOneWidget);
  });

  testWidgets('shopping suggestions modal clears protected results on denial',
      (tester) async {
    final backend = FakeBackend();
    addDefaults(backend);
    backend.json('GET', '/api/shopping/recent', ['Private suggestion']);
    final container = ProviderContainer(
        overrides: [apiClientProvider.overrideWithValue(backend.api())]);
    addTearDown(container.dispose);
    await tester.pumpWidget(UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ShoppingScreen())));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FloatingActionButton, 'Artikel'));
    await tester.pumpAndSettle();
    expect(find.text('Private suggestion'), findsOneWidget);
    backend.json('GET', '/api/shopping', {'detail': 'Kein Zugriff'},
        status: 403);
    await expectLater(container.read(shoppingProvider.notifier).refresh(),
        throwsA(isA<ApiException>()));
    await tester.pumpAndSettle();
    expect(find.text('Private suggestion'), findsNothing);
  });

  testWidgets('task creation modal clears retained people on denial',
      (tester) async {
    final backend = FakeBackend();
    addDefaults(backend);
    final container = ProviderContainer(
        overrides: [apiClientProvider.overrideWithValue(backend.api())]);
    addTearDown(container.dispose);
    await tester.pumpWidget(UncontrolledProviderScope(
        container: container, child: const MaterialApp(home: TasksScreen())));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FloatingActionButton, 'Aufgabe'));
    await tester.pumpAndSettle();
    expect(find.text('Sam'), findsOneWidget);
    backend.json('GET', '/api/tasks', {'detail': 'Kein Zugriff'}, status: 403);
    await expectLater(
        container.read(tasksProvider(TaskView.mine).notifier).refresh(),
        throwsA(isA<ApiException>()));
    await tester.pumpAndSettle();
    expect(find.text('Sam'), findsNothing);
  });

  for (final transition in ['logout', 'server', 'oidc']) {
    test('pending refresh persistence is serialized with $transition',
        () async {
      final store = DelayedWriteStore();
      final api = ApiClient(
          store: store,
          httpClient: MockClient((r) async {
            if (r.url.path == '/api/auth/refresh') {
              return jsonResponse({
                'access_token': 'rotated-old',
                'refresh_token': 'rotated-old-refresh'
              });
            }
            if (r.url.path == '/api/auth/oidc/exchange') {
              return jsonResponse({
                'access_token': 'new',
                'refresh_token': 'new-refresh',
                'user': meJson
              });
            }
            if (r.url.path == '/api/auth/logout') return jsonResponse(null);
            return jsonResponse({}, status: 401);
          }));
      final rejected =
          expectLater(api.today(), throwsA(isA<UnauthorizedException>()));
      await store.started.future;
      final change = switch (transition) {
        'logout' => api.logout(),
        'server' => api.setServer('https://new.test'),
        _ => api.exchangeOidcCode('test-code'),
      };
      await Future<void>.delayed(Duration.zero);
      store.release.complete();
      await change;
      await rejected;
      expect(store.access, transition == 'oidc' ? 'new' : isNull);
      expect(store.refresh, transition == 'oidc' ? 'new-refresh' : isNull);
      expect(store.url,
          transition == 'server' ? 'https://new.test' : 'https://old.test');
    });
  }
}
