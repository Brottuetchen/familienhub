import 'package:flutter/foundation.dart' show TargetPlatform, defaultTargetPlatform, kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../l10n/l10n.dart';
import '../../models/plugin_user.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';
import 'plugin_page_screen.dart';

/// Pages of active plugins for *More*. Errors (older server, offline) leave the list empty.
final pluginPagesProvider = FutureProvider.autoDispose<List<PluginPageInfo>>((ref) async {
  ref.watch(sessionScopeProvider);
  try {
    return await ref.watch(apiClientProvider).pluginPages();
  } catch (_) {
    return const [];
  }
});

/// How a plugin page address is opened; tests replace it.
typedef PageOpener = Future<bool> Function(Uri uri);

final pageOpenerProvider = Provider<PageOpener>((ref) => (uri) => launchUrl(uri, mode: LaunchMode.externalApplication));

/// Whether plugin pages open in the in-app WebView (Android/iOS). The web client opens a new tab; tests replace it.
final inAppPluginPagesProvider = Provider<bool>(
    (ref) => !kIsWeb && (defaultTargetPlatform == TargetPlatform.android || defaultTargetPlatform == TargetPlatform.iOS));

/// Asks the hub for a fresh, short-lived link (the page cannot use the app's login) and opens it in the in-app
/// WebView, or in the browser on the web.
Future<void> openPluginPage(BuildContext context, WidgetRef ref, String plugin, String page, {String path = ''}) async {
  try {
    final uri = await ref.read(apiClientProvider).pluginPageLink(plugin, page, path: path);
    if (ref.read(inAppPluginPagesProvider)) {
      if (!context.mounted) return;
      await Navigator.of(context).push(
          MaterialPageRoute<void>(builder: (_) => PluginPageScreen(plugin: plugin, page: page, initialUri: uri)));
      return;
    }
    final opened = await ref.read(pageOpenerProvider)(uri);
    if (!opened && context.mounted) showInfo(context, l10n.pluginPageOpenFailed);
  } catch (e) {
    if (context.mounted) showError(context, e);
  }
}
