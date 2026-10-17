import 'dart:async';

import 'package:familienhub/services/api_client.dart';
import 'package:familienhub/services/background.dart';
import 'package:familienhub/services/session_store.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:workmanager/workmanager.dart';

import 'helpers.dart';

// Exercise the registered production callback, including its real client and
// SecureSessionStore. Only native storage/widget channels and HTTP are fakes.
Future<bool> runScheduledTask(
        Future<http.Response> Function(http.Request) handler) =>
    http.runWithClient(() async {
      final reply = Completer<ByteData?>();
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .handlePlatformMessage(
        'dev.flutter.pigeon.workmanager_platform_interface.WorkmanagerFlutterApi.executeTask',
        WorkmanagerFlutterApi.pigeonChannelCodec
            .encodeMessage(['familienhub.widget-refresh', null]),
        reply.complete,
      );
      final result = WorkmanagerFlutterApi.pigeonChannelCodec
          .decodeMessage(await reply.future) as List;
      expect(result, [true]);
      return true;
    }, () => MockClient(handler));

class RecordingWorkmanager extends WorkmanagerPlatform {
  final calls = <String>[];

  @override
  Future<void> initialize(Function callbackDispatcher,
      {bool isInDebugMode = false}) async {
    calls.add('initialize');
  }

  @override
  Future<void> cancelByUniqueName(String uniqueName) async {
    calls.add('cancel:$uniqueName');
  }

  @override
  Future<void> registerPeriodicTask(String uniqueName, String taskName,
      {Duration? frequency, Duration? flexInterval, Map<String, dynamic>? inputData, Duration? initialDelay,
      Constraints? constraints, ExistingPeriodicWorkPolicy? existingWorkPolicy, BackoffPolicy? backoffPolicy,
      Duration? backoffPolicyDelay, String? tag, ForegroundServiceConfig? foregroundServiceConfig}) async {
    calls.add('periodic:$uniqueName:${frequency?.inMinutes}');
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const secureChannel =
      MethodChannel('plugins.it_nomads.com/flutter_secure_storage');
  const widgetChannel = MethodChannel('home_widget');
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  late Map<String, String> tokens;
  late List<String> mutations;
  late List<MethodCall> widgetCalls;

  setUpAll(callbackDispatcher);
  tearDownAll(() => WorkmanagerFlutterApi.setUp(null));

  setUp(() async {
    await setUpTestEnv();
    debugDefaultTargetPlatformOverride = TargetPlatform.android;
    tokens = {'access_token': 'old-access', 'refresh_token': 'old-refresh'};
    mutations = [];
    widgetCalls = [];
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('server_base_url', 'https://old.test');
    await prefs.setString('cache:new-session', 'do not delete');
    messenger.setMockMethodCallHandler(secureChannel, (call) async {
      final args = call.arguments as Map;
      final key = args['key'] as String?;
      switch (call.method) {
        case 'read':
          return tokens[key];
        case 'write':
          mutations.add('write:$key');
          tokens[key!] = args['value'] as String;
          return null;
        case 'delete':
          mutations.add('delete:$key');
          tokens.remove(key);
          return null;
        default:
          throw StateError('Unexpected secure storage call: ${call.method}');
      }
    });
    messenger.setMockMethodCallHandler(widgetChannel, (call) async {
      widgetCalls.add(call);
      return true;
    });
  });

  tearDown(() {
    debugDefaultTargetPlatformOverride = null;
    messenger.setMockMethodCallHandler(secureChannel, null);
    messenger.setMockMethodCallHandler(widgetChannel, null);
  });

  // Geändert (17.10.): Hintergrund-Aktualisierung ist wieder an – sitzungsgebunden und mit eigenem
  // Widget-Zugang statt Login-Tokens (siehe Tests unten). Vorher: nur alten Auftrag abbrechen.
  test('widget startup schedules the 15-minute session-bound refresh', () async {
    final previous = WorkmanagerPlatform.instance;
    final platform = RecordingWorkmanager();
    WorkmanagerPlatform.instance = platform;
    addTearDown(() => WorkmanagerPlatform.instance = previous);
    await startWidgetRefresh();
    expect(platform.calls, ['initialize', 'periodic:familienhub.widget-refresh:15']);
  });

  test(
      'scheduled background cannot restore tokens after pending 401 refresh and logout',
      () async {
    final refreshing = Completer<void>();
    final response = Completer<http.Response>();
    final requests = <http.Request>[];
    final task = runScheduledTask((request) async {
      requests.add(request);
      if (request.url.path == '/api/auth/refresh') {
        refreshing.complete();
        return response.future;
      }
      return jsonResponse({}, status: 401);
    });
    // A disabled task may finish without entering HTTP at all.
    await Future.any([refreshing.future, task]);
    final foreground = ApiClient(
        store: SecureSessionStore(),
        httpClient: MockClient((_) async => jsonResponse({})));
    await foreground.logout();
    mutations.clear();
    response.complete(jsonResponse({
      'access_token': 'restored-access',
      'refresh_token': 'restored-refresh',
    }));
    await task;
    expect(tokens, isEmpty);
    expect(mutations, isEmpty);
    expect(requests, isEmpty);
    expect(widgetCalls, isEmpty);
  });

  for (final changeServer in [false, true]) {
    test(
        'scheduled stale 401 cannot clear new ${changeServer ? 'server' : 'account'} session or cache',
        () async {
      final started = Completer<void>();
      final response = Completer<http.Response>();
      final requests = <http.Request>[];
      final task = runScheduledTask((request) async {
        requests.add(request);
        if (request.url.path == '/api/today') {
          started.complete();
          return response.future;
        }
        return jsonResponse({}, status: 401);
      });
      await Future.any([started.future, task]);
      final store = SecureSessionStore();
      if (changeServer) await store.saveBaseUrl('https://new.test');
      await store.saveTokens(access: 'new-access', refresh: 'new-refresh');
      mutations.clear();
      response.complete(jsonResponse({}, status: 401));
      await task;
      expect(tokens,
          {'access_token': 'new-access', 'refresh_token': 'new-refresh'});
      expect(mutations, isEmpty);
      expect(
          (await SharedPreferences.getInstance())
              .getString('cache:new-session'),
          'do not delete');
      expect(widgetCalls, isEmpty);
      expect(requests, isEmpty);
    });

    test(
        'scheduled old success is never published after ${changeServer ? 'server' : 'account'} change',
        () async {
      final started = Completer<void>();
      final response = Completer<http.Response>();
      final requests = <http.Request>[];
      final task = runScheduledTask((request) async {
        requests.add(request);
        if (request.url.path == '/api/today') {
          started.complete();
          return response.future;
        }
        return jsonResponse({'status': 'ok', 'groups': []});
      });
      await Future.any([started.future, task]);
      final store = SecureSessionStore();
      if (changeServer) await store.saveBaseUrl('https://new.test');
      await store.saveTokens(access: 'new-access', refresh: 'new-refresh');
      mutations.clear();
      response.complete(jsonResponse({
        'date': '2026-10-16',
        'tasks': {'status': 'ok', 'items': []},
        'shopping_open': 99,
      }));
      await task;
      expect(widgetCalls, isEmpty);
      expect(mutations, isEmpty);
      expect(requests, isEmpty);
      expect(tokens,
          {'access_token': 'new-access', 'refresh_token': 'new-refresh'});
      expect(
          (await SharedPreferences.getInstance())
              .getString('cache:new-session'),
          'do not delete');
    });
  }
}
