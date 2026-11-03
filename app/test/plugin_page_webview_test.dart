// In-app plugin pages: the navigation allow-list, the route -> screen mapping and the screen's close/back/refresh
// behaviour. The WebView platform is replaced by a fake (Flutter's recommended approach for webview_flutter tests).
import 'package:familienhub/providers/providers.dart';
import 'package:familienhub/screens/main_shell.dart';
import 'package:familienhub/screens/more/more_screen.dart';
import 'package:familienhub/screens/more/plugin_page_nav.dart';
import 'package:familienhub/screens/more/plugin_page_screen.dart';
import 'package:familienhub/screens/more/plugin_pages.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:plugin_platform_interface/plugin_platform_interface.dart';
import 'package:webview_flutter_platform_interface/webview_flutter_platform_interface.dart';

import 'helpers.dart';

class _FakeController extends PlatformWebViewController with MockPlatformInterfaceMixin {
  _FakeController(super.params) : super.implementation();
  final loaded = <Uri>[];
  final scripts = <String>[];
  // Decisions of the navigation delegate for our own about:blank loads (iOS asks for programmatic loads, too).
  final blankDecisions = <NavigationDecision>[];
  bool canGoBackNow = false;
  int goBackCalls = 0;
  JavaScriptMode? mode;
  _FakeDelegate? delegate;

  @override
  Future<void> setJavaScriptMode(JavaScriptMode javaScriptMode) async => mode = javaScriptMode;
  @override
  Future<void> setBackgroundColor(Color color) async {}
  @override
  Future<void> setPlatformNavigationDelegate(PlatformNavigationDelegate handler) async => delegate = handler as _FakeDelegate;
  @override
  Future<void> loadRequest(LoadRequestParams params) async {
    loaded.add(params.uri);
    if (params.uri.toString() == 'about:blank' && delegate?.onRequest != null) {
      blankDecisions.add(await delegate!.onRequest!(NavigationRequest(url: 'about:blank', isMainFrame: true)));
    }
  }

  @override
  Future<void> runJavaScript(String javaScript) async => scripts.add(javaScript);
  @override
  Future<bool> canGoBack() async => canGoBackNow;
  @override
  Future<void> goBack() async => goBackCalls++;
}

class _FakeDelegate extends PlatformNavigationDelegate with MockPlatformInterfaceMixin {
  _FakeDelegate(super.params) : super.implementation();
  NavigationRequestCallback? onRequest;
  PageEventCallback? onStarted;
  PageEventCallback? onFinished;
  HttpResponseErrorCallback? onHttp;
  WebResourceErrorCallback? onError;

  @override
  Future<void> setOnNavigationRequest(NavigationRequestCallback c) async => onRequest = c;
  @override
  Future<void> setOnPageStarted(PageEventCallback c) async => onStarted = c;
  @override
  Future<void> setOnPageFinished(PageEventCallback c) async => onFinished = c;
  @override
  Future<void> setOnHttpError(HttpResponseErrorCallback c) async => onHttp = c;
  @override
  Future<void> setOnWebResourceError(WebResourceErrorCallback c) async => onError = c;
  @override
  Future<void> setOnProgress(ProgressCallback c) async {}
  @override
  Future<void> setOnUrlChange(UrlChangeCallback c) async {}
  @override
  Future<void> setOnHttpAuthRequest(HttpAuthRequestCallback c) async {}
  @override
  Future<void> setOnSSlAuthError(SslAuthErrorCallback c) async {}
}

class _FakeWidget extends PlatformWebViewWidget with MockPlatformInterfaceMixin {
  _FakeWidget(super.params) : super.implementation();
  @override
  Widget build(BuildContext context) => const SizedBox.expand(key: Key('fake-webview'));
}

class _FakePlatform extends WebViewPlatform {
  _FakeController? controller;
  @override
  PlatformWebViewController createPlatformWebViewController(PlatformWebViewControllerCreationParams params) =>
      controller = _FakeController(params);
  @override
  PlatformNavigationDelegate createPlatformNavigationDelegate(PlatformNavigationDelegateCreationParams params) =>
      _FakeDelegate(params);
  @override
  PlatformWebViewWidget createPlatformWebViewWidget(PlatformWebViewWidgetCreationParams params) => _FakeWidget(params);
}

final _hub = Uri.parse('https://hub.test');
final _link = Uri.parse('https://hub.test/plugin-pages/TOKEN/');

FakeBackend _backend() {
  final b = FakeBackend();
  addDefaults(b);
  b.json('GET', '/api/plugin-pages', {
    'items': [
      {'plugin': 'recap', 'plugin_name': 'Rückblick', 'id': 'monthly', 'title': 'Monatsrückblick', 'icon': 'star'},
    ]
  });
  b.json('POST', '/api/plugin-pages/recap/monthly/link', {'url': '/plugin-pages/TOKEN/', 'expires_in': 900});
  return b;
}

Widget _app(FakeBackend b, Widget home) => ProviderScope(
      overrides: [
        apiClientProvider.overrideWithValue(b.api()),
        inAppPluginPagesProvider.overrideWithValue(true),
      ],
      child: MaterialApp(locale: const Locale('de', 'DE'), home: home),
    );

// The loading spinner animates forever, so pumpAndSettle would time out while a page is "loading".
Future<void> _settle(WidgetTester tester) async {
  for (var i = 0; i < 4; i++) {
    await tester.pump(const Duration(milliseconds: 200));
  }
}

void main() {
  late _FakePlatform platform;
  setUp(() {
    setUpTestEnv();
    platform = _FakePlatform();
    WebViewPlatform.instance = platform;
  });

  group('navigation allow-list', () {
    bool allowed(String url) => isPluginPageNavigationAllowed(Uri.parse(url), hub: _hub, link: _link);

    test('the signed prefix and everything below it is allowed', () {
      expect(allowed('https://hub.test/plugin-pages/TOKEN/'), isTrue);
      expect(allowed('https://hub.test/plugin-pages/TOKEN/2026-10/index.html'), isTrue);
      expect(allowed('https://hub.test/plugin-pages/TOKEN/img/a.jpg?x=1#3'), isTrue);
    });

    test('other servers, schemes, tokens and hub paths are not', () {
      expect(allowed('https://example.com/plugin-pages/TOKEN/'), isFalse);
      expect(allowed('http://hub.test/plugin-pages/TOKEN/'), isFalse);
      expect(allowed('https://hub.test:8443/plugin-pages/TOKEN/'), isFalse);
      expect(allowed('https://hub.test/plugin-pages/OTHER/'), isFalse);
      expect(allowed('https://hub.test/plugin-pages/TOKEN'), isFalse);
      expect(allowed('https://hub.test/api/auth/me'), isFalse);
      expect(allowed('https://hub.test/'), isFalse);
      expect(allowed('mailto:a@b.c'), isFalse);
      expect(allowed('https://hub.test.evil.com/plugin-pages/TOKEN/'), isFalse);
    });

    test('default ports compare equal, a link without token prefix allows nothing', () {
      expect(allowed('https://hub.test:443/plugin-pages/TOKEN/x'), isTrue);
      expect(isPluginPageNavigationAllowed(Uri.parse('https://hub.test/x'), hub: _hub, link: Uri.parse('https://hub.test/x')), isFalse);
    });
  });

  test('sub-path below the token and expired statuses', () {
    expect(pluginPageSubPath(Uri.parse('https://hub.test/plugin-pages/TOKEN/2026-10/index.html#4'), _link), '2026-10/index.html');
    expect(pluginPageSubPath(_link, _link), '');
    expect(pluginPageSubPath(Uri.parse('https://hub.test/elsewhere'), _link), '');
    expect([for (final s in [200, 401, 403, 404, 410, 500, null]) isExpiredLinkStatus(s)],
        [false, true, true, true, true, false, false]);
  });

  testWidgets('More -> plugin page opens the full-screen WebView with the signed link', (tester) async {
    await setScreenSize(tester, const Size(420, 900));
    final b = _backend();
    await tester.pumpWidget(_app(b, const MoreScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('more-page-recap-monthly')));
    await tester.pump();
    await tester.pump();
    expect(find.byType(PluginPageScreen), findsOneWidget);
    expect(platform.controller!.loaded, [Uri.parse('https://hub.test/plugin-pages/TOKEN/')]);
    expect(platform.controller!.mode, JavaScriptMode.unrestricted);
  });

  testWidgets('the notification route opens the screen with the requested sub-path', (tester) async {
    await setScreenSize(tester, const Size(420, 900));
    final b = _backend();
    b.json('POST', '/api/plugin-pages/recap/monthly/link', {'url': '/plugin-pages/TOKEN/2026-10', 'expires_in': 900});
    late WidgetRef captured;
    await tester.pumpWidget(_app(
        b,
        Consumer(builder: (context, ref, _) {
          captured = ref;
          return const MainShell(startPush: false);
        })));
    await tester.pumpAndSettle();
    openRoute(captured, '/plugin-page/recap/monthly?path=2026-10');
    await tester.pump();
    await tester.pump();
    expect(find.byType(PluginPageScreen), findsOneWidget);
    expect(bodyOf(b.sent('POST', '/api/plugin-pages/recap/monthly/link').single), {'path': '2026-10'});
    expect(platform.controller!.loaded.single.path, '/plugin-pages/TOKEN/2026-10');
  });

  group('screen', () {
    Future<void> openScreen(WidgetTester tester, FakeBackend b) async {
      await setScreenSize(tester, const Size(420, 900));
      await tester.pumpWidget(_app(
          b,
          Builder(
              builder: (context) => Scaffold(
                  body: TextButton(
                      onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(
                          builder: (_) => PluginPageScreen(plugin: 'recap', page: 'monthly', initialUri: _link))),
                      child: const Text('open'))))));
      await tester.tap(find.text('open'));
      await _settle(tester);
      expect(find.byType(PluginPageScreen), findsOneWidget);
    }

    testWidgets('shows the progress indicator until the page is loaded', (tester) async {
      await openScreen(tester, _backend());
      expect(find.byKey(const Key('plugin-page-loading')), findsOneWidget);
      platform.controller!.delegate!.onFinished!(_link.toString());
      await tester.pump();
      expect(find.byKey(const Key('plugin-page-loading')), findsNothing);
    });

    testWidgets('the close button closes the screen', (tester) async {
      await openScreen(tester, _backend());
      await tester.tap(find.byKey(const Key('plugin-page-close')));
      await _settle(tester);
      expect(find.byType(PluginPageScreen), findsNothing);
    });

    void expectStopped(_FakeController c) {
      expect(c.scripts, hasLength(1));
      expect(c.scripts.single, contains('pause()'));
      expect(c.scripts.single, contains("new CustomEvent('familienhub:close')"));
      expect(c.loaded.last, Uri.parse('about:blank'));
      expect(c.loaded.where((u) => u.toString() == 'about:blank'), hasLength(1));
      // our own about:blank load is allowed and never handed to the system (the rule would prevent + launch)
      expect(c.blankDecisions, [NavigationDecision.navigate]);
    }

    testWidgets('the close button pauses the media and unloads the page', (tester) async {
      final b = _backend();
      await openScreen(tester, b);
      final c = platform.controller!;
      expect(c.scripts, isEmpty);
      await tester.tap(find.byKey(const Key('plugin-page-close')));
      await _settle(tester);
      expect(find.byType(PluginPageScreen), findsNothing);
      expectStopped(c);
      expect(b.sent('POST', '/api/plugin-pages/recap/monthly/link'), isEmpty); // no expired-link refresh
    });

    testWidgets('back stops the page only when it cannot go back', (tester) async {
      await openScreen(tester, _backend());
      final c = platform.controller!;
      c.canGoBackNow = true;
      await tester.binding.handlePopRoute();
      await _settle(tester);
      expect(c.scripts, isEmpty);
      expect(c.loaded, [_link]);
      c.canGoBackNow = false;
      await tester.binding.handlePopRoute();
      await _settle(tester);
      expect(find.byType(PluginPageScreen), findsNothing);
      expectStopped(c);
    });

    testWidgets('a route popped from outside stops the page on dispose', (tester) async {
      final b = _backend();
      await openScreen(tester, b);
      final c = platform.controller!;
      final nav = tester.state<NavigatorState>(find.byType(Navigator));
      nav.pushReplacement(MaterialPageRoute<void>(builder: (_) => const Scaffold(body: Text('other'))));
      await _settle(tester);
      expect(find.byType(PluginPageScreen), findsNothing);
      expectStopped(c);
      expect(b.sent('POST', '/api/plugin-pages/recap/monthly/link'), isEmpty);
    });

    testWidgets('a load error while closing does not trigger a link refresh', (tester) async {
      final b = _backend();
      await openScreen(tester, b);
      final c = platform.controller!;
      await tester.tap(find.byKey(const Key('plugin-page-close')));
      c.delegate!.onError!(const WebResourceError(
          errorCode: -1, description: 'cancelled', errorType: WebResourceErrorType.unknown, isForMainFrame: true));
      await _settle(tester);
      expect(b.sent('POST', '/api/plugin-pages/recap/monthly/link'), isEmpty);
    });

    testWidgets('back goes back in the page history first, then closes', (tester) async {
      await openScreen(tester, _backend());
      platform.controller!.canGoBackNow = true;
      await tester.binding.handlePopRoute();
      await _settle(tester);
      expect(platform.controller!.goBackCalls, 1);
      expect(find.byType(PluginPageScreen), findsOneWidget);
      platform.controller!.canGoBackNow = false;
      await tester.binding.handlePopRoute();
      await _settle(tester);
      expect(platform.controller!.goBackCalls, 1);
      expect(find.byType(PluginPageScreen), findsNothing);
    });

    testWidgets('only the signed prefix is navigable, the rest is prevented (and opened externally)', (tester) async {
      await openScreen(tester, _backend());
      final d = platform.controller!.delegate!;
      NavigationRequest req(String url) => NavigationRequest(url: url, isMainFrame: true);
      expect(await d.onRequest!(req('https://hub.test/plugin-pages/TOKEN/2026-10/')), NavigationDecision.navigate);
      expect(await d.onRequest!(req('https://example.com/')), NavigationDecision.prevent);
      expect(await d.onRequest!(req('https://hub.test/api/auth/me')), NavigationDecision.prevent);
    });

    testWidgets('an expired link (HTTP 410) is renewed once and keeps the sub-path', (tester) async {
      final b = _backend();
      b.json('POST', '/api/plugin-pages/recap/monthly/link', {'url': '/plugin-pages/NEW/2026-10/index.html', 'expires_in': 900});
      await openScreen(tester, b);
      final c = platform.controller!;
      final page = Uri.parse('https://hub.test/plugin-pages/TOKEN/2026-10/index.html');
      c.delegate!.onStarted!(page.toString());
      c.delegate!.onHttp!(HttpResponseError(
          request: WebResourceRequest(uri: page),
          response: WebResourceResponse(uri: page, statusCode: 410)));
      await _settle(tester);
      expect(bodyOf(b.sent('POST', '/api/plugin-pages/recap/monthly/link').single), {'path': '2026-10/index.html'});
      expect(c.loaded.last, Uri.parse('https://hub.test/plugin-pages/NEW/2026-10/index.html'));
      // the new token is the allowed one now
      expect(await c.delegate!.onRequest!(NavigationRequest(url: 'https://hub.test/plugin-pages/NEW/x', isMainFrame: true)),
          NavigationDecision.navigate);
      // a second failure right away does not loop: it shows the retry button
      c.delegate!.onStarted!('https://hub.test/plugin-pages/NEW/2026-10/index.html');
      c.delegate!.onError!(const WebResourceError(
          errorCode: -2, description: 'offline', errorType: WebResourceErrorType.hostLookup, isForMainFrame: true));
      await _settle(tester);
      expect(b.sent('POST', '/api/plugin-pages/recap/monthly/link'), hasLength(1));
      expect(find.byKey(const Key('plugin-page-retry')), findsOneWidget);
    });

    testWidgets('a 404 for a sub-resource does not trigger a refresh', (tester) async {
      final b = _backend();
      await openScreen(tester, b);
      final c = platform.controller!;
      c.delegate!.onStarted!(_link.toString());
      final img = Uri.parse('https://hub.test/plugin-pages/TOKEN/img/missing.jpg');
      c.delegate!.onHttp!(HttpResponseError(
          request: WebResourceRequest(uri: img), response: WebResourceResponse(uri: img, statusCode: 404)));
      await _settle(tester);
      expect(b.sent('POST', '/api/plugin-pages/recap/monthly/link'), isEmpty);
    });
  });
}
