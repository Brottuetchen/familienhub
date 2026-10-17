import 'dart:async';

import 'package:familienhub/services/api_client.dart';
import 'package:familienhub/services/api_exceptions.dart';
import 'package:familienhub/services/session_store.dart';
import 'package:familienhub/providers/providers.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'helpers.dart';

class PausedBaseRead extends MemorySessionStore {
  final started = Completer<void>();
  final release = Completer<void>();
  bool pause = true;
  PausedBaseRead()
      : super(url: 'https://old.test', access: 'old', refresh: 'old-refresh');

  @override
  Future<String?> baseUrl() async {
    final value = url;
    if (pause) {
      pause = false;
      started.complete();
      await release.future;
    }
    return value;
  }
}

class PausedBaseWrite extends MemorySessionStore {
  final started = Completer<void>();
  final release = Completer<void>();
  PausedBaseWrite()
      : super(url: 'https://old.test', access: 'old', refresh: 'old-refresh');

  @override
  Future<void> saveBaseUrl(String value) async {
    started.complete();
    await release.future;
    await super.saveBaseUrl(value);
  }
}

void main() {
  setUp(setUpTestEnv);

  for (final oidc in [false, true]) {
    test('${oidc ? 'OIDC' : 'login'} waits for pending server persistence', () async {
      final store = PausedBaseWrite();
      final requests = <http.Request>[];
      final api = ApiClient(store: store, httpClient: MockClient((request) async {
        requests.add(request);
        return jsonResponse({
          'access_token': '${request.url.host}-access',
          'refresh_token': '${request.url.host}-refresh',
          'user': meJson,
        });
      }));
      final server = api.setServer('https://new.test');
      await store.started.future;
      final auth = oidc ? api.exchangeOidcCode('code') : api.login('user', 'password');
      await Future<void>.delayed(Duration.zero);
      final sentBeforePersistence = requests.toList();
      store.release.complete();
      await server;
      await auth;
      expect(sentBeforePersistence, isEmpty);
      expect(requests.single.url.toString(),
          'https://new.test/api/auth/${oidc ? 'oidc/exchange' : 'login'}');
      expect(requests.single.headers['Authorization'], isNull);
      expect(await store.baseUrl(), 'https://new.test');
      expect(await store.accessToken(), 'new.test-access');
      expect(await store.refreshToken(), 'new.test-refresh');
    });
  }

  test('OIDC start waits for pending server persistence', () async {
    final store = PausedBaseWrite();
    final requests = <http.Request>[];
    final api = ApiClient(store: store, httpClient: MockClient((request) async {
      requests.add(request);
      return jsonResponse({'url': 'https://auth.test/start'});
    }));
    final server = api.setServer('https://new.test');
    await store.started.future;
    final start = api.oidcStartUrl();
    await Future<void>.delayed(Duration.zero);
    final sentBeforePersistence = requests.toList();
    store.release.complete();
    await server;
    expect(await start, 'https://auth.test/start');
    expect(sentBeforePersistence, isEmpty);
    expect(requests.single.url.host, 'new.test');
    expect(requests.single.headers['Authorization'], isNull);
  });

  for (final oidc in [false, true]) {
    test('late ${oidc ? 'OIDC' : 'login'} response cannot restore a replaced session', () async {
      final store = MemorySessionStore(url: 'https://old.test');
      final started = Completer<void>();
      final response = Completer<http.Response>();
      final requests = <http.Request>[];
      final api = ApiClient(store: store, httpClient: MockClient((request) async {
        requests.add(request);
        if (request.url.host == 'old.test') {
          started.complete();
          return response.future;
        }
        return jsonResponse({
          'access_token': 'new', 'refresh_token': 'new-refresh', 'user': meJson,
        });
      }));
      final old = oidc ? api.exchangeOidcCode('old-code') : api.login('old-user', 'password');
      final rejected = expectLater(old, throwsA(isA<UnauthorizedException>()));
      await started.future;
      await api.setServer('https://new.test');
      await api.login('new-user', 'password');
      response.complete(jsonResponse({
        'access_token': 'old', 'refresh_token': 'old-refresh', 'user': meJson,
      }));
      await rejected;
      expect(requests.map((r) => r.url.host), ['old.test', 'new.test']);
      expect(requests.every((r) => r.headers['Authorization'] == null), isTrue);
      expect(await store.baseUrl(), 'https://new.test');
      expect(await store.accessToken(), 'new');
      expect(await store.refreshToken(), 'new-refresh');
    });
  }

  test('late startup cannot replace a newer login UI session', () async {
    final store = PausedBaseRead();
    final requests = <http.Request>[];
    final api = ApiClient(store: store, httpClient: MockClient((request) async {
      requests.add(request);
      if (request.url.path == '/api/auth/login') {
        return jsonResponse({'access_token': 'new', 'refresh_token': 'new-refresh', 'user': meJson});
      }
      return jsonResponse({}, status: 403);
    }));
    final session = SessionNotifier(api, autoStart: false);
    addTearDown(session.dispose);
    final startup = session.start();
    await store.started.future;
    await session.setServer('https://new.test');
    await session.login('new-user', 'password');
    store.release.complete();
    await startup;
    expect(session.state.phase, SessionPhase.loggedIn);
    expect(requests.map((r) => r.url.path), ['/api/auth/login']);
    expect(await store.accessToken(), 'new');
  });

  test('superseded notifier logout preserves the new logged-in UI session', () async {
    final store = PausedBaseRead();
    final api = ApiClient(store: store, httpClient: MockClient((request) async =>
      jsonResponse({'access_token': 'new', 'refresh_token': 'new-refresh', 'user': meJson})));
    final session = SessionNotifier(api, autoStart: false);
    addTearDown(session.dispose);
    final logout = session.logout();
    await store.started.future;
    await session.setServer('https://new.test');
    await session.login('new-user', 'password');
    store.release.complete();
    await logout;
    expect(session.state.phase, SessionPhase.loggedIn);
    expect(session.state.user?.id, meJson['id']);
    expect(await store.accessToken(), 'new');
  });

  test('superseded logout cannot send new credentials or clear new login', () async {
    final store = PausedBaseRead();
    final requests = <http.Request>[];
    final api = ApiClient(store: store, httpClient: MockClient((request) async {
      requests.add(request);
      return jsonResponse({
        'access_token': 'new',
        'refresh_token': 'new-refresh',
        'user': meJson,
      });
    }));
    final logout = api.logout();
    await store.started.future;
    await api.setServer('https://new.test');
    await api.login('new-user', 'password');
    store.release.complete();
    await logout;
    expect(requests.map((r) => r.url.toString()),
        ['https://new.test/api/auth/login']);
    expect(requests.single.headers['Authorization'], isNull);
    expect(await store.accessToken(), 'new');
    expect(await store.refreshToken(), 'new-refresh');
  });
}
