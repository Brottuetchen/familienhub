import 'dart:convert';

import 'package:familienhub/providers/providers.dart';
import 'package:familienhub/services/api_client.dart';
import 'package:familienhub/services/session_store.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:intl/intl.dart';
import 'package:shared_preferences/shared_preferences.dart';

typedef Handler = http.Response Function(http.Request request);

/// Nachgebautes Backend: Antworten je „METHODE /pfad“, alle Anfragen werden mitgeschrieben.
class FakeBackend {
  final Map<String, Handler> routes = {};
  final List<http.Request> requests = [];
  bool offline = false;

  void on(String method, String path, Handler handler) => routes['$method $path'] = handler;

  void json(String method, String path, Object? body, {int status = 200}) =>
      on(method, path, (_) => jsonResponse(body, status: status));

  List<http.Request> sent(String method, String path) =>
      requests.where((r) => r.method == method && r.url.path == path).toList();

  late final http.Client client = MockClient((request) async {
    if (offline) throw http.ClientException('Netzwerk nicht erreichbar', request.url);
    requests.add(request);
    final handler = routes['${request.method} ${request.url.path}'];
    if (handler == null) {
      return jsonResponse({'detail': 'Not Found ${request.method} ${request.url.path}'}, status: 404);
    }
    return handler(request);
  });

  ApiClient api({MemorySessionStore? store}) => ApiClient(
        httpClient: client,
        store: store ?? MemorySessionStore(url: 'https://hub.test', access: 'token-1', refresh: 'refresh-1'),
      );
}

http.Response jsonResponse(Object? body, {int status = 200}) => http.Response.bytes(
      utf8.encode(jsonEncode(body)),
      status,
      headers: {'content-type': 'application/json'},
    );

Map<String, dynamic> bodyOf(http.Request r) => jsonDecode(r.body) as Map<String, dynamic>;

Future<void> setUpTestEnv() async {
  SharedPreferences.setMockInitialValues({});
  Intl.defaultLocale = 'de_DE';
  await initializeDateFormatting('de_DE');
}

const meJson = {'id': 1, 'username': 'alex', 'full_name': 'Alex', 'is_admin': true};

/// Standardantworten, damit jeder Bildschirm etwas zum Anzeigen hat.
void addDefaults(FakeBackend backend) {
  backend.json('GET', '/api/auth/me', meJson);
  backend.json('GET', '/api/auth/people', [
    {'id': 1, 'username': 'alex', 'display_name': 'Alex'},
    {'id': 2, 'username': 'sam', 'display_name': 'Sam'},
  ]);
  backend.json('GET', '/api/today', {
    'date': '2026-10-14',
    'events': [],
    'tasks': {'status': 'ok', 'error': null, 'items': []},
    'meals': [],
    'shopping_open': 0,
    'reminders': [],
    'weather': null,
  });
  backend.json('GET', '/api/tasks/providers', {'items': [
    {'id': 'nextcloud', 'name': 'Nextcloud', 'account': '1', 'configured': true},
  ]});
  backend.json('GET', '/api/tasks', {'status': 'ok', 'error': null, 'items': []});
  backend.json('GET', '/api/shopping', {'status': 'ok', 'error': null, 'groups': []});
}

/// Bildschirm mit echtem ApiClient auf dem FakeBackend.
Widget appWith(ApiClient api, Widget child) => ProviderScope(
      overrides: [apiClientProvider.overrideWithValue(api)],
      child: MaterialApp(locale: const Locale('de', 'DE'), home: child),
    );

Future<void> setScreenSize(WidgetTester tester, Size size) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}
