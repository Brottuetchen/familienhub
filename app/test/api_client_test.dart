import 'dart:async';

import 'package:familienhub/models/common.dart';
import 'package:familienhub/services/api_client.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:familienhub/models/task.dart';
import 'package:familienhub/services/api_exceptions.dart';
import 'package:familienhub/services/session_store.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

void main() {
  setUp(setUpTestEnv);

  test('parses tasks status items', () async {
    final backend = FakeBackend()
      ..json('GET', '/api/tasks', {
        'status': 'ok',
        'error': null,
        'items': [
          {
            'uid': 'a1',
            'title': 'Müll rausbringen',
            'notes': 'Gelber Sack',
            'due': '2026-10-20',
            'priority': 5,
            'done': false,
            'list': {'name': 'Familie', 'kind': 'family'},
            'created_by': 2,
            'assignee': 1,
            'etag': null,
          },
        ],
      });
    final result = await backend.api().tasks(TaskView.forMe);

    expect(backend.requests.single.url.queryParameters['view'], 'for_me');
    expect(result.fromCache, isFalse);
    expect(result.data.status, SourceStatus.ok);
    final task = result.data.items.single;
    expect(task.uid, 'a1');
    expect(task.title, 'Müll rausbringen');
    expect(task.notes, 'Gelber Sack');
    expect(task.due, DateTime(2026, 10, 20));
    expect(task.dueIsDate, isTrue);
    expect(task.priority, 5);
    expect(task.listName, 'Familie');
    expect(task.listKind, 'family');
    expect(task.createdBy, 2);
    expect(task.assignee, 1);

    backend.json('GET', '/api/tasks', {'status': 'unavailable', 'error': 'CalDAV down', 'items': []});
    final down = await backend.api().tasks(TaskView.mine);
    expect(down.data.status, SourceStatus.unavailable);
    expect(down.data.error, 'CalDAV down');
    expect(down.data.items, isEmpty);
  });

  test('maps 409 no_write_access to WriteAccessException', () async {
    final backend = FakeBackend()
      ..json('POST', '/api/tasks', {
        'detail': {'error': 'no_write_access', 'list': 'Sam'}
      }, status: 409);

    await expectLater(
      backend.api().createTask(title: 'Pakete holen', assigneeId: 2),
      throwsA(isA<WriteAccessException>()
          .having((e) => e.listName, 'listName', 'Sam')
          .having((e) => e.message, 'message', contains('nicht für dich freigegeben'))),
    );
    expect(bodyOf(backend.requests.single)['assignee_id'], 2);
  });

  test('maps 409 no_caldav_account to NoCalDavAccountException', () async {
    final backend = FakeBackend()
      ..json('POST', '/api/calendar/events', {
        'detail': {'error': 'no_caldav_account'}
      }, status: 409);
    await expectLater(
      backend.api().createEvent(
          title: 'Zahnarzt', start: DateTime(2026, 10, 20, 10), end: DateTime(2026, 10, 20, 11), allDay: false),
      throwsA(isA<NoCalDavAccountException>()),
    );
  });

  test('refreshes token on 401 once', () async {
    final backend = FakeBackend();
    backend.on('GET', '/api/auth/me', (r) {
      return r.headers['Authorization'] == 'Bearer token-2'
          ? jsonResponse(meJson)
          : jsonResponse({'detail': 'expired'}, status: 401);
    });
    backend.json('POST', '/api/auth/refresh',
        {'access_token': 'token-2', 'token_type': 'bearer', 'refresh_token': 'refresh-2'});
    final store = MemorySessionStore(url: 'https://hub.test', access: 'token-1', refresh: 'refresh-1');

    final user = await backend.api(store: store).me();

    expect(user.username, 'alex');
    expect(backend.sent('POST', '/api/auth/refresh'), hasLength(1));
    expect(bodyOf(backend.sent('POST', '/api/auth/refresh').single), {'refresh_token': 'refresh-1'});
    expect(backend.sent('GET', '/api/auth/me'), hasLength(2));
    expect(store.access, 'token-2');
    expect(store.refresh, 'refresh-2');
  });

  test('ends session when refresh is rejected', () async {
    final backend = FakeBackend()
      ..json('GET', '/api/auth/me', {'detail': 'expired'}, status: 401)
      ..json('POST', '/api/auth/refresh', {'detail': 'Invalid'}, status: 401);
    final store = MemorySessionStore(url: 'https://hub.test', access: 'token-1', refresh: 'refresh-1');
    final api = backend.api(store: store);
    final loggedOut = Completer<void>();
    api.loggedOut.listen((_) => loggedOut.complete());

    await expectLater(api.me(), throwsA(isA<UnauthorizedException>()));
    expect(backend.sent('POST', '/api/auth/refresh'), hasLength(1));
    expect(backend.sent('GET', '/api/auth/me'), hasLength(1));
    expect(store.access, isNull);
    expect(store.refresh, isNull);
    await loggedOut.future.timeout(const Duration(seconds: 1));
  });

  test('login sends client app and stores refresh token', () async {
    final backend = FakeBackend()
      ..json('POST', '/api/auth/login', {
        'access_token': 'a',
        'token_type': 'bearer',
        'refresh_token': 'r',
        'user': meJson,
      });
    final store = MemorySessionStore(url: 'https://hub.test');
    final user = await backend.api(store: store).login('alex', 'pw');

    expect(bodyOf(backend.requests.single), {'username': 'alex', 'password': 'pw', 'client': 'app'});
    expect(user.displayName, 'Alex');
    expect(store.access, 'a');
    expect(store.refresh, 'r');
  });

  test('returns cache when offline', () async {
    final backend = FakeBackend()
      ..json('GET', '/api/shopping', {
        'status': 'ok',
        'error': null,
        'groups': [
          {
            'key': 'manual',
            'entity': 'todo.einkauf',
            'items': [
              {'uid': 's1', 'summary': 'Milch', 'status': 'needs_action'},
            ],
          },
        ],
      });
    final api = backend.api();
    final online = await api.shopping();
    expect(online.fromCache, isFalse);

    backend.offline = true;
    final offline = await api.shopping();

    expect(offline.fromCache, isTrue);
    expect(offline.cachedAt, isNotNull);
    expect(offline.data.groups.single.items.single.summary, 'Milch');
  });

  test('offline without cache throws OfflineException', () async {
    final backend = FakeBackend()..offline = true;
    await expectLater(backend.api().today(), throwsA(isA<OfflineException>()));
  });

  test('write while offline is remembered instead of failing (#32)', () async {
    final backend = FakeBackend()..offline = true;
    final api = backend.api();
    expect(await api.addShoppingItem('Brot'), isFalse);
    expect(await api.completeTask('a1'), isFalse);
    expect(api.pending.map((c) => c.kind), ['shopping_add', 'task_complete']);
    // Nicht merkbare Schreibaktionen scheitern offline weiterhin sichtbar
    await expectLater(api.addMeal(DateTime(2026, 10, 20), 'Suppe'), throwsA(isA<OfflineException>()));
  });

  test('createEvent sends local time with offset and all-day as dates', () async {
    final backend = FakeBackend()..json('POST', '/api/calendar/events', {'uid': 'e1'}, status: 201);
    final api = backend.api();
    await api.createEvent(
        title: 'Elternabend', start: DateTime(2026, 10, 20, 19), end: DateTime(2026, 10, 20, 20), allDay: false);
    await api.createEvent(
        title: 'Ausflug', start: DateTime(2026, 10, 24), end: DateTime(2026, 10, 25), allDay: true);

    final timed = bodyOf(backend.requests[0]);
    expect(timed['start'], startsWith('2026-10-20T19:00:00'));
    expect(timed['start'], matches(RegExp(r'[+-]\d\d:\d\d$')));
    expect(timed['all_day'], isFalse);
    final allDay = bodyOf(backend.requests[1]);
    expect(allDay['start'], '2026-10-24');
    expect(allDay['end'], '2026-10-25');
  });

  test('normalizes server address', () {
    expect(normalizeBaseUrl(' hub.example.org/ '), 'https://hub.example.org');
    expect(normalizeBaseUrl('http://10.0.0.5:8000/'), 'http://10.0.0.5:8000');
  });

  const native = Task(uid: 'remote', title: 'Nativ', provider: 'habitica', account: 'own');

  test('native scoring never replays after auth refresh or follows redirects', () async {
    final backend = FakeBackend();
    backend.json('POST', '/api/tasks/remote/actions', {'detail': 'Abgelaufen'}, status: 401);
    backend.json('POST', '/api/auth/refresh', {'access_token': 'new', 'refresh_token': 'new-refresh'});
    final api = backend.api();
    await expectLater(api.nativeTaskAction(native, 'up'), throwsA(isA<ApiException>()));
    expect(backend.sent('POST', '/api/tasks/remote/actions'), hasLength(1));
    expect(backend.sent('POST', '/api/auth/refresh'), hasLength(1));
    expect(backend.sent('POST', '/api/tasks/remote/actions').single.followRedirects, isFalse);
    backend.json('POST', '/api/tasks/remote/actions', {'detail': 'Unklarer Redirect'}, status: 307);
    await expectLater(api.nativeTaskAction(native, 'up'), throwsA(isA<ApiException>()));
    expect(api.nativeTaskBlocked(native.account), isTrue);
    await expectLater(api.nativeTaskAction(native, 'up'), throwsA(isA<ApiException>()));
    expect(backend.sent('POST', '/api/tasks/remote/actions'), hasLength(2));
  });

  test('native pending and timeout locks survive another caller and widget remount', () async {
    final response = Completer<http.Response>();
    var calls = 0;
    final api = ApiClient(store: MemorySessionStore(url: 'https://hub.test', access: 'token'),
      timeout: const Duration(milliseconds: 30), httpClient: MockClient((request) async {
        calls++;
        return response.future;
      }));
    final first = api.nativeTaskAction(native, 'up');
    expect(api.nativeTaskBlocked(native.account), isTrue);
    await expectLater(api.nativeTaskAction(native, 'down'), throwsA(isA<ApiException>()));
    await expectLater(first, throwsA(isA<OfflineException>()));
    expect(api.nativeTaskBlocked(native.account), isTrue);
    await expectLater(api.nativeTaskAction(native, 'up'), throwsA(isA<ApiException>()));
    expect(calls, 1);
    response.complete(jsonResponse({'accepted': true}));
  });

  test('native action keeps the account lock through its authoritative read', () async {
    final read = Completer<http.Response>();
    var posts = 0;
    final api = ApiClient(
      store: MemorySessionStore(url: 'https://hub.test', access: 'token'),
      httpClient: MockClient((request) async {
        if (request.method == 'POST') {
          posts++;
          return jsonResponse({'accepted': true});
        }
        if (request.method == 'GET' && request.url.path == '/api/habitica/tasks') return read.future;
        return jsonResponse({'status': 'ok', 'items': []});
      }),
    );

    final first = api.nativeTaskActionAndRefresh(native, 'up');
    await Future<void>.delayed(Duration.zero);
    expect(api.nativeTaskBlocked(native.account), isTrue);

    final second = api.nativeTaskActionAndRefresh(native, 'down');
    await expectLater(second, throwsA(isA<ApiException>()));
    expect(posts, 1);

    read.complete(jsonResponse({'status': 'ok', 'error': null, 'items': []}));
    await expectLater(first, throwsA(isA<NativeTaskConfirmedReadException>()));
  });

  test('native save and delete keep the account lock through their authoritative reads', () async {
    ApiClient clientFor(Completer<http.Response> read, List<String> methods) {
      return ApiClient(
        store: MemorySessionStore(url: 'https://hub.test', access: 'token'),
        httpClient: MockClient((request) async {
          if (request.method == 'GET') return read.future;
          methods.add(request.method);
          return request.method == 'DELETE' ? http.Response('', 204) : jsonResponse({'uid': 'new', 'accepted': true});
        }),
      );
    }

    final saveRead = Completer<http.Response>();
    final saveMethods = <String>[];
    final saveApi = clientFor(saveRead, saveMethods);
    final save = saveApi.saveNativeTask('own', {'type': 'todo', 'text': 'Neu'});
    await Future<void>.delayed(Duration.zero);
    await expectLater(saveApi.deleteTask('remote', provider: 'habitica', account: 'own'), throwsA(isA<ApiException>()));
    expect(saveMethods, ['POST']);
    saveRead.complete(jsonResponse({'status': 'ok', 'error': null, 'items': [
      {'uid': 'new', 'title': 'Neu', 'provider': 'habitica', 'account': 'own'},
    ]}));
    await save;

    final deleteRead = Completer<http.Response>();
    final deleteMethods = <String>[];
    final deleteApi = clientFor(deleteRead, deleteMethods);
    final delete = deleteApi.deleteTask('remote', provider: 'habitica', account: 'own');
    await Future<void>.delayed(Duration.zero);
    await expectLater(deleteApi.saveNativeTask('own', {'type': 'todo', 'text': 'Neu'}), throwsA(isA<ApiException>()));
    expect(deleteMethods, ['DELETE']);
    deleteRead.complete(jsonResponse({'status': 'ok', 'error': null, 'items': []}));
    await delete;
  });

  test('reconciliation cannot race a native read or restore an old session outcome', () async {
    final read = Completer<http.Response>();
    final api = ApiClient(
      store: MemorySessionStore(url: 'https://hub.test', access: 'token'),
      httpClient: MockClient((request) async {
        if (request.method == 'POST') return jsonResponse({'accepted': true});
        return read.future;
      }),
    );

    final action = api.nativeTaskActionAndRefresh(native, 'checklist_edit', itemId: 'item-1');
    await Future<void>.delayed(Duration.zero);
    await expectLater(api.reconcileHabiticaTasks(native.account), throwsA(isA<ApiException>()));
    final session = api.setServer('https://new.test');
    read.complete(jsonResponse({'status': 'unavailable', 'error': 'old read', 'items': []}));
    await session;
    await expectLater(action, throwsA(isA<NativeTaskConfirmedReadException>()));
    expect(api.nativeTaskBlocked(native.account), isFalse);
  });

  test('confirmed native mutation blocks retry until explicit read reconciliation', () async {
    final backend = FakeBackend()
      ..json('POST', '/api/tasks/remote/actions', {'accepted': true})
      ..json('GET', '/api/habitica/tasks', {'status': 'unavailable', 'error': 'read failed', 'items': []});
    final api = backend.api();

    await expectLater(
      api.nativeTaskActionAndRefresh(native, 'checklist_edit', itemId: 'item-1'),
      throwsA(isA<NativeTaskConfirmedReadException>()),
    );
    expect(backend.sent('POST', '/api/tasks/remote/actions'), hasLength(1));
    expect(api.nativeTaskBlocked(native.account), isTrue);
    await expectLater(api.nativeTaskActionAndRefresh(native, 'checklist_edit', itemId: 'item-1'), throwsA(isA<ApiException>()));
    expect(backend.sent('POST', '/api/tasks/remote/actions'), hasLength(1));

    backend.json('GET', '/api/habitica/tasks', {
      'status': 'ok', 'error': null,
      'items': [
        {'uid': 'remote', 'title': 'Nativ', 'provider': 'habitica', 'account': 'own', 'native': {'type': 'todo', 'checklist': []}, 'actions': []},
      ],
    });
    final refreshed = await api.reconcileHabiticaTasks(native.account);
    expect(refreshed.isOk, isTrue);
    expect(api.nativeTaskBlocked(native.account), isFalse);

    backend.json('POST', '/api/tasks/remote/actions', {'accepted': true});
    backend.json('GET', '/api/habitica/tasks', {
      'status': 'ok', 'error': null,
      'items': [
        {'uid': 'remote', 'title': 'Nativ', 'provider': 'habitica', 'account': 'own', 'native': {'type': 'todo', 'checklist': []}, 'actions': []},
      ],
    });
    await api.nativeTaskActionAndRefresh(native, 'checklist_edit', itemId: 'item-1');
    expect(backend.sent('POST', '/api/tasks/remote/actions'), hasLength(2));
  });

  test('confirmed native mutation also blocks when refreshed task is missing', () async {
    final backend = FakeBackend()
      ..json('POST', '/api/tasks/remote/actions', {'accepted': true})
      ..json('GET', '/api/habitica/tasks', {'status': 'ok', 'error': null, 'items': []});
    final api = backend.api();

    await expectLater(api.nativeTaskActionAndRefresh(native, 'checklist_delete', itemId: 'item-1'), throwsA(isA<NativeTaskConfirmedReadException>()));
    await expectLater(api.nativeTaskActionAndRefresh(native, 'checklist_delete', itemId: 'item-1'), throwsA(isA<ApiException>()));
    expect(backend.sent('POST', '/api/tasks/remote/actions'), hasLength(1));
  });

  test('native save rejects an ok refresh that omits the created task ID', () async {
    final backend = FakeBackend()
      ..json('POST', '/api/tasks', {'uid': 'created', 'title': 'Neu'})
      ..json('GET', '/api/habitica/tasks', {'status': 'ok', 'error': null, 'items': []});
    final api = backend.api();

    await expectLater(
      api.saveNativeTask('own', {'type': 'todo', 'text': 'Neu'}),
      throwsA(isA<NativeTaskConfirmedReadException>()),
    );
    expect(api.nativeTaskBlocked('own'), isTrue);
    await expectLater(api.saveNativeTask('own', {'type': 'todo', 'text': 'Neu'}), throwsA(isA<ApiException>()));
    expect(backend.sent('POST', '/api/tasks'), hasLength(1));
  });

  test('direct native action rejects an ok refresh that omits the target task', () async {
    final backend = FakeBackend()
      ..json('POST', '/api/tasks/remote/actions', {'accepted': true})
      ..json('GET', '/api/habitica/tasks', {'status': 'ok', 'error': null, 'items': []});
    final api = backend.api();

    await expectLater(api.nativeTaskAction(native, 'up'), throwsA(isA<NativeTaskConfirmedReadException>()));
    expect(api.nativeTaskBlocked('own'), isTrue);
    await expectLater(api.nativeTaskAction(native, 'up'), throwsA(isA<ApiException>()));
    expect(backend.sent('POST', '/api/tasks/remote/actions'), hasLength(1));
  });

  test('native delete rejects an ok refresh that still contains the target task', () async {
    final backend = FakeBackend()
      ..json('DELETE', '/api/tasks/remote', null, status: 204)
      ..json('GET', '/api/habitica/tasks', {
        'status': 'ok', 'error': null,
        'items': [{'uid': 'remote', 'title': 'Nativ', 'provider': 'habitica', 'account': 'own'}],
      });
    final api = backend.api();

    await expectLater(api.deleteTask('remote', provider: 'habitica', account: 'own'), throwsA(isA<NativeTaskConfirmedReadException>()));
    expect(api.nativeTaskBlocked('own'), isTrue);
    await expectLater(api.deleteTask('remote', provider: 'habitica', account: 'own'), throwsA(isA<ApiException>()));
    expect(backend.sent('DELETE', '/api/tasks/remote'), hasLength(1));
  });

  test('native create uses the POST response ID for authoritative validation', () async {
    final backend = FakeBackend()
      ..json('POST', '/api/tasks', {'uid': 'created', 'title': 'Neu'})
      ..json('GET', '/api/habitica/tasks', {
        'status': 'ok', 'error': null,
        'items': [{'uid': 'created', 'title': 'Neu', 'provider': 'habitica', 'account': 'own'}],
      });
    final api = backend.api();

    await api.saveNativeTask('own', {'type': 'todo', 'text': 'Neu'});
    expect(api.nativeTaskBlocked('own'), isFalse);
  });

  test('native create edit and delete carry account, version and unique operation IDs', () async {
    final backend = FakeBackend();
    backend.json('POST', '/api/tasks', {'uid': 'new'}, status: 201);
    backend.json('PATCH', '/api/tasks/remote', {'uid': 'remote'});
    backend.json('DELETE', '/api/tasks/remote', null, status: 204);
    var reads = 0;
    backend.on('GET', '/api/habitica/tasks', (_) {
      reads++;
      return jsonResponse({
        'status': 'ok', 'error': null,
        'items': [
          if (reads < 3) {'uid': 'new', 'title': 'Tee', 'provider': 'habitica', 'account': 'own'},
          if (reads < 3) {'uid': 'remote', 'title': 'Nativ', 'provider': 'habitica', 'account': 'own'},
        ],
      });
    });
    final api = backend.api();
    await api.saveNativeTask('own', {'type': 'reward', 'text': 'Tee', 'value': 5});
    await api.saveNativeTask('own', {'notes': 'Nur Notizen'}, uid: 'remote', expectedVersion: 'v1');
    await api.deleteTask('remote', provider: 'habitica', account: 'own');
    final created = backend.sent('POST', '/api/tasks').single;
    final updated = backend.sent('PATCH', '/api/tasks/remote').single;
    final deleted = backend.sent('DELETE', '/api/tasks/remote').single;
    for (final request in [created, updated, deleted]) {
      expect(request.url.queryParameters['provider'], 'habitica');
      expect(request.url.queryParameters['account'], 'own');
      expect(request.followRedirects, isFalse);
    }
    expect(bodyOf(updated)['native'], {'notes': 'Nur Notizen'});
    expect(bodyOf(updated).containsKey('title'), isFalse);
    expect(bodyOf(updated)['expected_version'], 'v1');
    final operations = [bodyOf(created)['operation_id'], bodyOf(updated)['operation_id'], deleted.url.queryParameters['operation_id']];
    expect(operations.toSet(), hasLength(3));
    for (final id in operations) { expect(id, matches(RegExp(r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'))); }
  });

}
