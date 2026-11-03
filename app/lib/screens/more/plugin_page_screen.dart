import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:webview_flutter_android/webview_flutter_android.dart';
import 'package:webview_flutter_wkwebview/webview_flutter_wkwebview.dart';

import '../../l10n/l10n.dart';
import '../../providers/providers.dart';
import 'plugin_page_nav.dart';

/// A plugin page in a full-screen in-app WebView (Android/iOS), so a story page can autoplay its soundtrack.
///
/// [initialUri] is the absolute, signed `/plugin-pages/<token>/…` link. Only the hub's origin below the link's token
/// prefix is shown; anything else opens in the system. When the link has expired (HTTP 401/403/404/410 on the main
/// frame, or a load error) a fresh link is fetched once and the current sub-path is reloaded.
class PluginPageScreen extends ConsumerStatefulWidget {
  final String plugin;
  final String page;
  final Uri initialUri;
  const PluginPageScreen({super.key, required this.plugin, required this.page, required this.initialUri});

  @override
  ConsumerState<PluginPageScreen> createState() => _PluginPageScreenState();
}

class _PluginPageScreenState extends ConsumerState<PluginPageScreen> {
  late final WebViewController _controller;
  late Uri _link = widget.initialUri;
  late final Uri _hub = widget.initialUri;
  Uri _current = Uri();
  int _progress = 0;
  bool _retried = false;
  bool _failed = false;
  bool _loadHadError = false;

  @override
  void initState() {
    super.initState();
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);
    _current = _link;
    _controller = _buildController();
    unawaited(_controller.loadRequest(_link));
  }

  WebViewController _buildController() {
    late final PlatformWebViewControllerCreationParams params;
    if (WebViewPlatform.instance is WebKitWebViewPlatform) {
      params = WebKitWebViewControllerCreationParams(
        allowsInlineMediaPlayback: true,
        mediaTypesRequiringUserAction: const <PlaybackMediaTypes>{},
      );
    } else {
      params = const PlatformWebViewControllerCreationParams();
    }
    final c = WebViewController.fromPlatformCreationParams(params)
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(Colors.black)
      ..setNavigationDelegate(NavigationDelegate(
        onNavigationRequest: _onNavigationRequest,
        onProgress: (p) {
          if (mounted) setState(() => _progress = p);
        },
        onPageStarted: (url) {
          _loadHadError = false;
          _current = Uri.tryParse(url) ?? _current;
        },
        onUrlChange: (change) {
          final u = change.url == null ? null : Uri.tryParse(change.url!);
          if (u != null) _current = u;
        },
        onPageFinished: (_) {
          if (!mounted) return;
          setState(() => _progress = 100);
          if (!_failed && !_loadHadError) _retried = false; // a good load re-arms the single retry
        },
        onHttpError: (e) {
          if (isExpiredLinkStatus(e.response?.statusCode) && _isMainFrame(e.request?.uri)) _linkFailed();
        },
        onWebResourceError: (e) {
          if (e.isForMainFrame ?? false) _linkFailed();
        },
      ));
    final platform = c.platform;
    if (platform is AndroidWebViewController) {
      unawaited(platform.setMediaPlaybackRequiresUserGesture(false));
    }
    return c;
  }

  bool _isMainFrame(Uri? uri) => uri != null && uri.path == _current.path && uri.host == _current.host;

  FutureOr<NavigationDecision> _onNavigationRequest(NavigationRequest request) {
    final target = Uri.tryParse(request.url);
    if (target == null) return NavigationDecision.prevent;
    if (isPluginPageNavigationAllowed(target, hub: _hub, link: _link)) return NavigationDecision.navigate;
    if (request.isMainFrame) {
      unawaited(launchUrl(target, mode: LaunchMode.externalApplication).catchError((_) => false));
      return NavigationDecision.prevent;
    }
    return NavigationDecision.prevent; // sub-frames/resources outside the allow-list are not loaded
  }

  /// The signed link was refused or the load failed: ask for a fresh one once and keep the sub-path.
  Future<void> _linkFailed() async {
    if (!mounted) return;
    _loadHadError = true;
    if (_retried) {
      setState(() => _failed = true); // the fresh link failed as well: show the retry button
      return;
    }
    _retried = true;
    try {
      final sub = pluginPageSubPath(_current, _link);
      final fresh = await ref.read(apiClientProvider).pluginPageLink(widget.plugin, widget.page, path: sub);
      if (!mounted) return;
      _link = fresh;
      _current = fresh;
      setState(() {
        _failed = false;
        _progress = 0;
      });
      await _controller.loadRequest(fresh);
    } catch (_) {
      if (mounted) setState(() => _failed = true);
    }
  }

  Future<void> _back() async {
    if (await _controller.canGoBack()) {
      await _controller.goBack();
    } else if (mounted) {
      Navigator.of(context).pop();
    }
  }

  @override
  void dispose() {
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) unawaited(_back());
      },
      child: Scaffold(
        backgroundColor: Colors.black,
        body: Stack(children: [
          Positioned.fill(child: WebViewWidget(controller: _controller)),
          if (_progress < 100 && !_failed)
            const Positioned.fill(
              child: ColoredBox(color: Colors.black, child: Center(child: CircularProgressIndicator(key: Key('plugin-page-loading')))),
            ),
          if (_failed)
            Positioned.fill(
              child: ColoredBox(
                color: Colors.black,
                child: Center(
                  child: Column(mainAxisSize: MainAxisSize.min, children: [
                    Text(l10n.pluginPageLoadFailed, style: const TextStyle(color: Colors.white)),
                    const SizedBox(height: 12),
                    FilledButton(
                      key: const Key('plugin-page-retry'),
                      onPressed: () {
                        _retried = false;
                        setState(() => _failed = false);
                        unawaited(_linkFailed());
                      },
                      child: Text(l10n.pluginPageRetry),
                    ),
                  ]),
                ),
              ),
            ),
          SafeArea(
            child: Align(
              alignment: Alignment.topLeft,
              child: Padding(
                padding: const EdgeInsets.all(8),
                child: IconButton.filled(
                  key: const Key('plugin-page-close'),
                  tooltip: l10n.pluginPageClose,
                  style: IconButton.styleFrom(backgroundColor: Colors.black54, foregroundColor: Colors.white),
                  icon: const Icon(Icons.close),
                  onPressed: () => Navigator.of(context).pop(),
                ),
              ),
            ),
          ),
        ]),
      ),
    );
  }
}
