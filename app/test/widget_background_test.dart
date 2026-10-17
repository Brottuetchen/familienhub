import 'dart:async';
import 'dart:convert';

import 'package:familienhub/core/theme/app_theme.dart';
import 'package:familienhub/models/themes.dart';
import 'package:familienhub/services/api_client.dart';
import 'package:familienhub/services/background.dart';
import 'package:familienhub/services/home_widgets.dart';
import 'package:familienhub/services/session_store.dart';
import 'package:familienhub/services/widget_access.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart' show ThemeData;
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'helpers.dart';

ThemeData themeFor(Map<String, dynamic> style) => AppTheme.fromSpec(ThemeSpec(id: 'x', name: 'x', colors: const {
      'primary': '#7C3AED', 'secondary': '#F59E0B', 'background': '#FBF4E8', 'surface': '#FFFFFF',
      'surfaceHigh': '#FFF4D6', 'border': '#111111',
    }, style: style));

/// Sitzungsgebundene Widget-Aktualisierung im Hintergrund mit eigenem Widget-Zugang.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const secureChannel = MethodChannel('plugins.it_nomads.com/flutter_secure_storage');
  const widgetChannel = MethodChannel('home_widget');
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  late Map<String, String> secure;
  late Map<String, Object?> widgetData;
  late List<String> secureWrites;

  setUp(() async {
    await setUpTestEnv();
    debugDefaultTargetPlatformOverride = TargetPlatform.android;
    secure = {
      'access_token': 'login-access',
      'refresh_token': 'login-refresh',
      'widget_api_token': 'fhp_widget',
      'widget_api_token_id': '7',
    };
    widgetData = {'widget_session': 'sess-1'};
    secureWrites = [];
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('server_base_url', 'https://hub.test');
    messenger.setMockMethodCallHandler(secureChannel, (call) async {
      final args = call.arguments as Map;
      final key = args['key'] as String?;
      switch (call.method) {
        case 'read':
          return secure[key];
        case 'write':
          secureWrites.add('write:$key');
          secure[key!] = args['value'] as String;
          return null;
        case 'delete':
          secureWrites.add('delete:$key');
          secure.remove(key);
          return null;
      }
      return null;
    });
    messenger.setMockMethodCallHandler(widgetChannel, (call) async {
      final args = (call.arguments as Map?) ?? const {};
      switch (call.method) {
        case 'saveWidgetData':
          widgetData[args['id'] as String] = args['data'];
          return true;
        case 'getWidgetData':
          return widgetData[args['id'] as String] ?? args['defaultValue'];
        default:
          return true;
      }
    });
  });

  tearDown(() {
    debugDefaultTargetPlatformOverride = null;
    messenger.setMockMethodCallHandler(secureChannel, null);
    messenger.setMockMethodCallHandler(widgetChannel, null);
  });

  http.Response ok(Object body) => http.Response.bytes(utf8.encode(jsonEncode(body)), 200,
      headers: {'content-type': 'application/json'});
  const today = {'date': '2026-10-17', 'tasks': {'status': 'ok', 'items': [{'uid': 'a', 'title': 'Müll'}]},
    'shopping_open': 2, 'events': [], 'meals': []};
  const shopping = {'status': 'ok', 'groups': [{'key': 'manual', 'items': [
    {'uid': 's1', 'summary': 'Milch', 'status': 'needs_action'}]}]};

  test('veröffentlicht mit dem Widget-Zugang und fasst die Login-Tokens nie an', () async {
    final requests = <http.Request>[];
    await backgroundWidgetRefresh(client: MockClient((r) async {
      requests.add(r);
      return r.url.path == '/api/today' ? ok(today) : ok(shopping);
    }));
    expect(requests.map((r) => r.url.path), ['/api/today', '/api/shopping']);
    expect(requests.every((r) => r.headers['Authorization'] == 'Bearer fhp_widget'), isTrue);
    expect(widgetData['today_tasks'], '☐ Müll');
    expect(widgetData['shopping_items'], '• Milch');
    expect(secureWrites, isEmpty);
    expect(secure['refresh_token'], 'login-refresh');
  });

  test('Abmelden während des Abrufs: nichts wird veröffentlicht', () async {
    final hold = Completer<http.Response>();
    final task = backgroundWidgetRefresh(client: MockClient((r) async {
      if (r.url.path == '/api/today') return hold.future;
      return ok(shopping);
    }));
    await Future<void>.delayed(const Duration(milliseconds: 10));
    await HomeWidgets.endSession(); // Vordergrund meldet ab
    hold.complete(ok(today));
    await task;
    expect(widgetData['today_tasks'], isNull);
    expect(widgetData['shopping_items'], isNull);
  });

  test('widerrufener Zugang (401) leert die Widgets und löscht den Zugang', () async {
    widgetData['today_tasks'] = '☐ Alt';
    await backgroundWidgetRefresh(client: MockClient((r) async => http.Response('{}', 401)));
    expect(widgetData['widget_session'], '');
    expect(widgetData['today_tasks'], isNull);
    expect(secure.containsKey('widget_api_token'), isFalse);
    expect(secure['access_token'], 'login-access'); // Anmeldung bleibt unberührt
  });

  test('401 nach Sitzungswechsel lässt die neue Sitzung in Ruhe', () async {
    final hold = Completer<http.Response>();
    final task = backgroundWidgetRefresh(client: MockClient((r) async => hold.future));
    await Future<void>.delayed(const Duration(milliseconds: 10));
    widgetData['widget_session'] = 'sess-2'; // neue Anmeldung
    secure['widget_api_token'] = 'fhp_new';
    hold.complete(http.Response('{}', 401));
    await task;
    expect(widgetData['widget_session'], 'sess-2');
    expect(secure['widget_api_token'], 'fhp_new');
  });

  test('ohne Widget-Zugang: kein Netz, kein Widget-Speicher', () async {
    secure.remove('widget_api_token');
    var calls = 0;
    await backgroundWidgetRefresh(client: MockClient((r) async {
      calls++;
      return ok(today);
    }));
    expect(calls, 0);
    expect(widgetData.keys, ['widget_session']);
  });

  test('Abmelden widerruft den Zugang beim Hub und leert die Widgets', () async {
    widgetData['today_events'] = '• Kita-Fest';
    final deleted = <String>[];
    final api = ApiClient(
      store: MemorySessionStore(url: 'https://hub.test', access: 'login-access'),
      httpClient: MockClient((r) async {
        if (r.method == 'DELETE') deleted.add(r.url.path);
        return ok({});
      }),
    );
    await WidgetAccess.revoke(api);
    expect(deleted, ['/api/auth/api-tokens/7']);
    expect(widgetData['widget_session'], '');
    expect(widgetData['today_events'], isNull);
    expect(secure.containsKey('widget_api_token'), isFalse);
  });

  test('Widget-Stil folgt dem Theme (Neo-Brutalism: Rahmen, harter Schatten, farbiger Kopf)', () async {
    const neo = {
      'card': {'radius': 14, 'border': 3, 'shadow': 'hard', 'header': 'band'},
      'accents': ['#8B5CF6'],
    };
    final theme = themeFor(neo);
    final s = widgetStyle(theme);
    expect(s['w_border_w'], '3');
    expect(s['w_shadow'], 'hard');
    expect(s['w_radius'], '14');
    expect(s['w_band'], isNotEmpty);
  });
}
