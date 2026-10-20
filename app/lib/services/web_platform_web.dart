import 'dart:async';
import 'dart:convert';
import 'dart:js_interop';
import 'dart:js_interop_unsafe';
import 'dart:typed_data';

import 'package:web/web.dart' as web;

import 'page_base_url.dart';

@JS('JSON.stringify')
external JSString _stringify(JSAny? value);

bool get webPushSupported =>
    web.window.has('PushManager') && web.window.navigator.has('serviceWorker') && web.window.has('Notification');

String? webPushPermission() => web.window.has('Notification') ? web.Notification.permission : null;

bool isStandalone() {
  if (web.window.matchMedia('(display-mode: standalone)').matches) return true;
  // iOS Safari: navigator.standalone
  final standalone = web.window.navigator.getProperty<JSAny?>('standalone'.toJS);
  return standalone != null && standalone.isA<JSBoolean>() && (standalone as JSBoolean).toDart;
}

Uint8List _base64UrlDecode(String input) {
  var s = input.replaceAll('-', '+').replaceAll('_', '/');
  while (s.length % 4 != 0) {
    s += '=';
  }
  return base64Decode(s);
}

/// Fragt (bei [prompt]) die Erlaubnis ab, registriert `push-sw.js` (relativ zur Basis-URL der Seite) und liefert das Abo als JSON.
/// Muss bei [prompt] direkt aus einem Tipp heraus aufgerufen werden (iOS verlangt eine Nutzeraktion).
Future<Map<String, dynamic>?> subscribeWebPush(String vapidPublicKey, {bool prompt = true}) async {
  if (!webPushSupported) return null;
  var permission = web.Notification.permission;
  if (permission != 'granted') {
    if (!prompt) return null;
    permission = (await web.Notification.requestPermission().toDart).toDart;
    if (permission != 'granted') return null;
  }
  final container = web.window.navigator.serviceWorker;
  await container.register('push-sw.js'.toJS).toDart;
  final reg = await container.ready.toDart;
  var sub = await reg.pushManager.getSubscription().toDart;
  sub ??= await reg.pushManager
      .subscribe(web.PushSubscriptionOptionsInit(
        userVisibleOnly: true,
        applicationServerKey: _base64UrlDecode(vapidPublicKey).toJS,
      ))
      .toDart;
  return jsonDecode(_stringify(sub.toJSON()).toDart) as Map<String, dynamic>;
}

/// Ziele aus angetippten Mitteilungen, die der Service Worker an die offene Seite meldet.
Stream<String> serviceWorkerRoutes() {
  if (!web.window.navigator.has('serviceWorker')) return const Stream.empty();
  final controller = StreamController<String>.broadcast();
  web.window.navigator.serviceWorker.addEventListener(
    'message',
    ((web.MessageEvent event) {
      final data = event.data.dartify();
      if (data is Map && data['route'] is String) controller.add(data['route'] as String);
    }).toJS,
  );
  return controller.stream;
}

Map<String, String> startQuery() => Uri.base.queryParameters;

void clearStartQuery() {
  final uri = Uri.base;
  if (uri.query.isEmpty) return;
  final rest = uri.hasFragment ? '${uri.path}#${uri.fragment}' : uri.path;
  web.window.history.replaceState(null, '', rest);
}

/// Server address of the web app: the page's base URL, which includes the Home Assistant ingress prefix.
String? pageBaseUrl() => serverBaseFromPage(web.document.baseURI);
