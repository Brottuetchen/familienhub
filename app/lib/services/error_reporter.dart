import 'dart:async';

import 'package:flutter/foundation.dart';

import 'api_client.dart';

/// Unerwartete App-Fehler ans Protokoll der Verwaltung melden (nur angemeldet, je Meldung einmal pro Sitzung,
/// höchstens 10 pro Sitzung). Der Server schwärzt und begrenzt zusätzlich.
class ErrorReporter {
  static ApiClient? api;
  static final _sent = <String>{};
  static const maxPerSession = 10;

  static void install() {
    final previous = FlutterError.onError;
    FlutterError.onError = (details) {
      previous?.call(details);
      report(details.exceptionAsString(), details.stack);
    };
    final previousPlatform = PlatformDispatcher.instance.onError;
    PlatformDispatcher.instance.onError = (error, stack) {
      report(error.toString(), stack);
      return previousPlatform?.call(error, stack) ?? false;
    };
  }

  static void report(String message, StackTrace? stack) {
    final client = api;
    if (client == null || _sent.length >= maxPerSession) return;
    final key = message.length > 200 ? message.substring(0, 200) : message;
    if (!_sent.add(key)) return;
    unawaited(client.reportClientError(message: message, stack: stack?.toString()).catchError((Object _) {}));
  }

  @visibleForTesting
  static void reset() => _sent.clear();
}
