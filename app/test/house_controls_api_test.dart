import 'dart:async';
import 'dart:convert';

import 'package:familienhub/services/api_client.dart';
import 'package:familienhub/services/api_exceptions.dart';
import 'package:familienhub/services/session_store.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'helpers.dart';

void main() {
  setUp(setUpTestEnv);

  test('house POST never replays after successful token refresh', () async {
    final backend = FakeBackend();
    backend.json('POST', '/api/house/actions', {'detail': 'expired'}, status: 401);
    backend.json('POST', '/api/auth/refresh', {'access_token': 'token-2', 'refresh_token': 'refresh-2'});
    final api = backend.api();
    await expectLater(api.houseAction('scene.evening', 'activate'), throwsA(isA<ApiException>()));
    expect(backend.sent('POST', '/api/house/actions'), hasLength(1));
    expect(backend.sent('POST', '/api/auth/refresh'), hasLength(1));
    expect(await api.store.accessToken(), 'token-2');
  });

  test('house metadata never falls back to stored or held controls', () async {
    final backend = FakeBackend();
    backend.json('GET', '/api/house/controls', {'status': 'ok', 'items': [
      {'entity_id': 'light.lamp', 'name': 'Lampe', 'state': 'on', 'actions': ['turn_off']},
    ]});
    final api = backend.api();
    expect((await api.houseControls()).items, hasLength(1));
    expect((await SharedPreferences.getInstance()).getKeys(), isEmpty);
    backend.offline = true;
    await expectLater(api.houseControls(), throwsA(isA<http.ClientException>()));
    expect(await api.cached('house-controls', (j) => j), isNull);
  });

  test('house accepted action invalidates today snapshot', () async {
    final backend = FakeBackend();
    addDefaults(backend);
    backend.json('POST', '/api/house/actions', {'accepted': true});
    final api = backend.api();
    await api.today();
    expect(await api.cached('today', (j) => j), isNotNull);
    await api.houseAction('light.lamp', 'turn_on');
    expect(await api.cached('today', (j) => j), isNull);
  });

  test('house timeout is failure and never resends', () async {
    var posts = 0;
    final api = ApiClient(
      store: MemorySessionStore(url: 'https://hub.test', access: 'token', refresh: 'refresh'),
      timeout: const Duration(milliseconds: 5),
      httpClient: MockClient((request) async {
        posts++;
        await Future<void>.delayed(const Duration(milliseconds: 25));
        return jsonResponse({'accepted': true});
      }),
    );
    await expectLater(api.houseAction('script.evening', 'activate'), throwsA(isA<OfflineException>()));
    await Future<void>.delayed(const Duration(milliseconds: 30));
    expect(posts, 1);
  });

  test('delayed house controls cannot cross logout or server change', () async {
    final reply = Completer<http.Response>();
    final started = Completer<void>();
    final api = ApiClient(
      store: MemorySessionStore(url: 'https://hub.test', access: 'token'),
      httpClient: MockClient((request) {
        started.complete();
        return reply.future;
      }),
    );
    final pending = api.houseControls();
    final failure = expectLater(pending, throwsA(isA<UnauthorizedException>()));
    await started.future;
    await api.setServer('https://other.test');
    reply.complete(jsonResponse({'status': 'ok', 'items': []}));
    await failure;
  });

  test('house device POST forbids redirect replay in production transport', () async {
    final api = ApiClient(
      store: MemorySessionStore(url: 'https://hub.test', access: 'token'),
      httpClient: MockClient((request) async {
        expect(request.followRedirects, isFalse);
        return jsonResponse({'accepted': true});
      }),
    );
    await api.houseAction('light.lamp', 'turn_on');
  });
  test('shared house action path rejects concurrent submissions', () async {
    final reply = Completer<http.Response>();
    final started = Completer<void>();
    var posts = 0;
    final api = ApiClient(
      store: MemorySessionStore(url: 'https://hub.test', access: 'token'),
      httpClient: MockClient((request) {
        posts++;
        if (!started.isCompleted) started.complete();
        return reply.future;
      }),
    );
    final first = api.houseAction('script.evening', 'activate');
    await started.future;
    final second = api.houseAction('script.evening', 'activate')
        .then<Object?>((_) => null, onError: (Object e) => e);
    await Future<void>.delayed(Duration.zero);
    reply.complete(jsonResponse({'accepted': true}));
    await first;
    final rejection = await second;
    expect(posts, 1);
    expect(rejection, isA<ApiException>());
  });

  for (final status in [200, 409]) {
    test('house action guard releases after $status without replay', () async {
      var posts = 0;
      final api = ApiClient(
        store: MemorySessionStore(url: 'https://hub.test', access: 'token'),
        httpClient: MockClient((_) async {
          posts++;
          return jsonResponse({'accepted': true}, status: status);
        }),
      );
      for (var i = 0; i < 2; i++) {
        final pending = api.houseAction('script.evening', 'activate');
        expect(api.houseActionPending, isTrue);
        if (status == 200) {
          await pending;
        } else {
          await expectLater(pending, throwsA(isA<ApiException>()));
        }
        expect(api.houseActionPending, isFalse);
        expect(posts, i + 1);
      }
    });
  }

  test('old session completion cannot release newer house action guard', () async {
    final oldReply = Completer<http.Response>();
    final newReply = Completer<http.Response>();
    final oldStarted = Completer<void>();
    final newStarted = Completer<void>();
    var posts = 0;
    final api = ApiClient(
      store: MemorySessionStore(url: 'https://hub.test', access: 'token'),
      httpClient: MockClient((request) async {
        if (request.url.path == '/api/auth/login') {
          return jsonResponse({'access_token': 'new-token', 'user': meJson});
        }
        posts++;
        if (posts == 1) { oldStarted.complete(); return oldReply.future; }
        newStarted.complete();
        return newReply.future;
      }),
    );
    final old = expectLater(api.houseAction('script.evening', 'activate'),
        throwsA(isA<UnauthorizedException>()));
    await oldStarted.future;
    await api.setServer('https://other.test');
    expect(api.houseActionPending, isFalse);
    await api.login('alex', 'test-password');
    final current = api.houseAction('scene.evening', 'activate');
    await newStarted.future;
    oldReply.complete(jsonResponse({'accepted': true}));
    await old;
    expect(api.houseActionPending, isTrue);
    await expectLater(api.houseAction('scene.evening', 'activate'), throwsA(isA<ApiException>()));
    expect(posts, 2);
    newReply.complete(jsonResponse({'accepted': true}));
    await current;
    expect(api.houseActionPending, isFalse);
  });

  test('a new action clears the previous outcome before its response', () async {
    final reply = Completer<http.Response>();
    var posts = 0;
    final api = ApiClient(
      store: MemorySessionStore(url: 'https://hub.test', access: 'token'),
      httpClient: MockClient((_) async {
        if (++posts == 1) return jsonResponse({'detail': 'timeout'}, status: 409);
        return reply.future;
      }),
    );
    await expectLater(api.houseAction('script.evening', 'activate'), throwsA(isA<ApiException>()));
    expect(api.houseActionFailed, isTrue);
    final current = api.houseAction('scene.evening', 'activate');
    expect(api.houseActionFailed, isFalse);
    expect(api.houseActionPending, isTrue);
    await expectLater(api.houseAction('scene.evening', 'activate'), throwsA(isA<ApiException>()));
    expect(api.houseActionFailed, isFalse, reason: 'a blocked duplicate is not a failed device action');
    reply.complete(jsonResponse({'accepted': true}));
    await current;
    expect(api.houseActionFailed, isFalse);
    expect(api.houseActionPending, isFalse);
    expect(posts, 2);
  });

  for (final oldStatus in [200, 409]) {
    test('old session $oldStatus cannot erase a newer failed outcome', () async {
      final oldReply = Completer<http.Response>();
      final oldStarted = Completer<void>();
      var posts = 0;
      final api = ApiClient(
        store: MemorySessionStore(url: 'https://hub.test', access: 'token'),
        httpClient: MockClient((request) async {
          if (request.url.path == '/api/auth/login') {
            return jsonResponse({'access_token': 'new-token', 'user': meJson});
          }
          posts++;
          if (posts == 1) { oldStarted.complete(); return oldReply.future; }
          return jsonResponse({'detail': 'private new failure'}, status: 409);
        }),
      );
      final old = expectLater(api.houseAction('script.evening', 'activate'),
          throwsA(isA<UnauthorizedException>()));
      await oldStarted.future;
      await api.setServer('https://other.test');
      await api.login('alex', 'test-password');
      expect(api.houseActionFailed, isFalse);
      await expectLater(api.houseAction('scene.evening', 'activate'), throwsA(isA<ApiException>()));
      expect(api.houseActionFailed, isTrue);
      oldReply.complete(jsonResponse({'detail': 'private old failure'}, status: oldStatus));
      await old;
      expect(api.houseActionFailed, isTrue);
      expect(api.houseActionPending, isFalse);
      expect(posts, 2);
      await api.setServer('https://third.test');
      expect(api.houseActionFailed, isFalse);
    });
  }

  test('different devices switch in parallel, each exactly once', () async {
    final replies = <String, Completer<http.Response>>{'light.lamp': Completer(), 'switch.plug': Completer()};
    final posts = <String>[];
    final api = ApiClient(
      store: MemorySessionStore(url: 'https://hub.test', access: 'token'),
      httpClient: MockClient((request) {
        final entity = (jsonDecode(request.body) as Map)['entity_id'] as String;
        posts.add(entity);
        return replies[entity]!.future;
      }),
    );
    final lamp = api.houseAction('light.lamp', 'turn_on');
    final plug = api.houseAction('switch.plug', 'turn_on');
    await Future<void>.delayed(Duration.zero);
    expect(posts, ['light.lamp', 'switch.plug']);
    expect(api.houseActionPendingFor('light.lamp'), isTrue);
    await expectLater(api.houseAction('light.lamp', 'turn_off'), throwsA(isA<ApiException>()));
    replies['switch.plug']!.complete(jsonResponse({'accepted': true}));
    await plug;
    expect(api.houseActionPendingFor('switch.plug'), isFalse);
    expect(api.houseActionPendingFor('light.lamp'), isTrue);
    replies['light.lamp']!.complete(jsonResponse({'accepted': true, 'control': {
      'entity_id': 'light.lamp', 'name': 'Lampe', 'state': 'on', 'actions': ['turn_off'], 'brightness': null,
    }}));
    expect((await lamp)!.state, 'on');
    expect(posts, hasLength(2));
  });

  test('confirmation for another device is ignored', () async {
    final api = ApiClient(
      store: MemorySessionStore(url: 'https://hub.test', access: 'token'),
      httpClient: MockClient((_) async => jsonResponse({'accepted': true, 'control': {
        'entity_id': 'light.other', 'name': 'X', 'state': 'on', 'actions': [],
      }})),
    );
    expect(await api.houseAction('light.lamp', 'turn_on'), isNull);
  });
}
