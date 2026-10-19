import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../l10n/l10n.dart';
import '../../models/store.dart';
import '../../providers/providers.dart';
import '../../providers/theme_provider.dart';
import '../../widgets/common.dart';
import '../more/plugin_install_screen.dart';
import 'store_screen.dart';

/// Ask before installing anything from a source the maintainers have not reviewed. true = go ahead.
Future<bool> confirmUnverified(BuildContext context, String body) async =>
    await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        key: const Key('store-unverified-dialog'),
        icon: const Icon(Icons.warning_amber_rounded, color: Colors.orange),
        title: Text(l10n.storeUnverifiedTitle),
        content: SingleChildScrollView(child: Text(body)),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: Text(l10n.cancel)),
          FilledButton(
            key: const Key('store-unverified-confirm'),
            onPressed: () => Navigator.pop(ctx, true),
            child: Text(l10n.storeContinueAnyway),
          ),
        ],
      ),
    ) ==
    true;

/// One store entry: screenshots, description, version, repository, what it needs, and Install / Update.
class StoreDetailScreen extends ConsumerStatefulWidget {
  final StoreItem item;
  final Future<void> Function(Uri url)? openUrl; // tests replace the browser
  final bool installerEnabled; // PLUGIN_INSTALL_ENABLED; themes stay installable without it
  const StoreDetailScreen({super.key, required this.item, this.openUrl, this.installerEnabled = true});

  @override
  ConsumerState<StoreDetailScreen> createState() => _StoreDetailScreenState();
}

class _StoreDetailScreenState extends ConsumerState<StoreDetailScreen> {
  late StoreItem _item = widget.item;
  late final Future<StoreDetails> _detailsFuture = ref.read(apiClientProvider).storeDetails(widget.item);
  final _pages = PageController();
  int _page = 0;
  bool _busy = false;

  @override
  void dispose() {
    _pages.dispose();
    super.dispose();
  }

  void _markInstalled(String version) {
    setState(() => _item = StoreItem(
          source: _item.source,
          verified: _item.verified,
          type: _item.type,
          id: _item.id,
          name: _item.name,
          summary: _item.summary,
          description: _item.description,
          author: _item.author,
          repo: _item.repo,
          version: _item.version,
          sha: _item.sha,
          shortSha: _item.shortSha,
          tags: _item.tags,
          minHubVersion: _item.minHubVersion,
          compatible: _item.compatible,
          screenshots: _item.screenshots,
          state: StoreState.installed,
          installedVersion: version,
        ));
    ref.invalidate(storeProvider);
  }

  Future<void> _install() async {
    final item = _item;
    var acknowledged = false;
    if (!item.verified) {
      if (!await confirmUnverified(context, l10n.storeUnverifiedInstallBody(item.name)) || !mounted) return;
      acknowledged = true;
    }
    if (item.isPlugin) {
      // Same review (full-access warning, trust checkbox) and settings form as a pasted link, at the pinned commit
      final done = await Navigator.of(context).push<bool>(MaterialPageRoute(
          builder: (_) => PluginInstallScreen(storeItem: item, acknowledgedUnverified: acknowledged)));
      if (done == true && mounted) {
        ref.invalidate(adminPluginsProvider);
        ref.invalidate(modulesProvider);
        _markInstalled(item.version);
      }
      return;
    }
    setState(() => _busy = true);
    Map<String, dynamic>? result;
    final ok = await runAction(context, () async {
      result = await ref.read(apiClientProvider).storeInstall(item, item.sha, acknowledgeUnverified: acknowledged);
    });
    if (!mounted) return;
    setState(() => _busy = false);
    if (ok) {
      ref.invalidate(themesProvider);
      _markInstalled(item.version);
      final name = ((result?['theme'] as Map?)?['name'] as String?) ?? item.name;
      showInfo(context, result?['updated'] == true ? l10n.storeThemeUpdated(name) : l10n.storeThemeInstalled(name));
    }
  }

  Widget _action(BuildContext context) {
    final item = _item;
    if (_busy) return const Center(child: HubLoader());
    final (String label, IconData icon, bool enabled) = switch (item.state) {
      _ when !item.compatible => (l10n.storeIncompatible(item.minHubVersion), Icons.block, false),
      StoreState.available || StoreState.update when item.isPlugin && !widget.installerEnabled =>
        (l10n.pluginInstallOff, Icons.block, false),
      StoreState.available => (l10n.install, Icons.download_outlined, true),
      StoreState.update => (l10n.storeUpdate, Icons.upgrade, true),
      StoreState.installed => (l10n.storeInstalled, Icons.check, false),
      StoreState.conflict => (l10n.storeConflict, Icons.block, false),
    };
    return SizedBox(
      width: double.infinity,
      child: FilledButton.icon(
        key: const Key('store-action'),
        onPressed: enabled ? _install : null,
        icon: Icon(icon),
        label: Text(label, textAlign: TextAlign.center),
      ),
    );
  }

  Widget _screenshots(BuildContext context) {
    final shots = _item.screenshots;
    final scheme = Theme.of(context).colorScheme;
    return Column(children: [
      ClipRRect(
        borderRadius: BorderRadius.circular(12),
        child: AspectRatio(
          aspectRatio: 16 / 9,
          child: PageView.builder(
            key: const Key('store-carousel'),
            controller: _pages,
            itemCount: shots.length,
            onPageChanged: (i) => setState(() => _page = i),
            itemBuilder: (_, i) => Semantics(
              label: l10n.storeScreenshot(i + 1),
              image: true,
              child: StoreScreenshot(
                path: shots[i],
                placeholder: _item.isPlugin ? Icons.extension_outlined : Icons.palette_outlined,
                fit: BoxFit.contain,
              ),
            ),
          ),
        ),
      ),
      if (shots.length > 1)
        Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
            for (var i = 0; i < shots.length; i++)
              Container(
                width: 8,
                height: 8,
                margin: const EdgeInsets.symmetric(horizontal: 3),
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: i == _page ? scheme.primary : scheme.outlineVariant,
                ),
              ),
          ]),
        ),
    ]);
  }

  Widget _info(BuildContext context, IconData icon, String title, Widget body) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Icon(icon, size: 20, color: Theme.of(context).colorScheme.primary),
          const SizedBox(width: 12),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(title, style: Theme.of(context).textTheme.labelLarge),
              body,
            ]),
          ),
        ]),
      );

  Widget _warning(BuildContext context, Key key, Color color, String title, String body) => Container(
        key: key,
        margin: const EdgeInsets.only(top: 12),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.10),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: color.withValues(alpha: 0.5)),
        ),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Icon(Icons.warning_amber_rounded, color: color),
          const SizedBox(width: 10),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(title, style: Theme.of(context).textTheme.titleSmall),
              const SizedBox(height: 4),
              Text(body),
            ]),
          ),
        ]),
      );

  Widget _details(BuildContext context) {
    final muted = TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant);
    return FutureBuilder<StoreDetails>(
      future: _detailsFuture,
      builder: (context, snap) {
        if (snap.connectionState != ConnectionState.done) {
          return const Padding(padding: EdgeInsets.all(12), child: Center(child: HubLoader()));
        }
        final d = snap.data;
        if (d == null) {
          return Padding(
            key: const Key('store-details-failed'),
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Text(l10n.storeDetailsFailed, style: muted),
          );
        }
        if (!_item.isPlugin) {
          if (d.colors.isEmpty) return const SizedBox.shrink();
          return _info(
            context,
            Icons.palette_outlined,
            l10n.storeColors,
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Wrap(spacing: 6, runSpacing: 6, children: [
                for (final c in d.colors.values)
                  Container(
                    width: 28,
                    height: 28,
                    decoration: BoxDecoration(
                      color: _hex(c),
                      shape: BoxShape.circle,
                      border: Border.all(color: Theme.of(context).colorScheme.outlineVariant),
                    ),
                  ),
              ]),
            ),
          );
        }
        return Column(key: const Key('store-details'), children: [
          if (d.capabilities.isNotEmpty)
            _info(context, Icons.extension_outlined, l10n.pluginProvides, Text(d.capabilities.join(', '), style: muted)),
          _info(context, Icons.public, l10n.pluginHosts,
              Text(d.hosts.isEmpty ? l10n.pluginNoHosts : d.hosts.join(', '), style: muted)),
          _info(context, Icons.tune, l10n.storeNeeds,
              Text(d.settings.isEmpty ? l10n.storeNoSettings : d.settings.join(', '), style: muted)),
        ]);
      },
    );
  }

  static Color _hex(String value) {
    final v = int.tryParse(value.replaceFirst('#', ''), radix: 16);
    return v == null ? Colors.transparent : Color(0xFF000000 | v);
  }

  @override
  Widget build(BuildContext context) {
    final item = _item;
    final theme = Theme.of(context);
    final muted = TextStyle(color: theme.colorScheme.onSurfaceVariant);
    final open = widget.openUrl ?? (u) => launchUrl(u, mode: LaunchMode.externalApplication);
    return Scaffold(
      appBar: AppBar(title: Text(item.name, maxLines: 1, overflow: TextOverflow.ellipsis)),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
        children: [
          if (item.screenshots.isNotEmpty) _screenshots(context),
          const SizedBox(height: 12),
          Text(item.name, key: const Key('store-detail-name'), style: theme.textTheme.headlineSmall),
          if (item.author.isNotEmpty) Text(l10n.pluginBy(item.author), style: muted),
          const SizedBox(height: 8),
          Wrap(spacing: 6, runSpacing: 6, children: storeBadges(context, item)),
          if (item.state == StoreState.update && item.installedVersion != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(l10n.storeUpdateFromTo(item.installedVersion!, item.version), key: const Key('store-update-note')),
            ),
          const SizedBox(height: 16),
          _action(context),
          if (!item.verified)
            _warning(context, const Key('store-unverified-warning'), Colors.orange, l10n.storeUnverifiedTitle,
                l10n.storeUnverifiedSourceBody),
          if (item.isPlugin)
            _warning(context, const Key('store-plugin-warning'), theme.colorScheme.error, l10n.pluginWarningTitle,
                l10n.pluginWarningBody),
          if (item.description.isNotEmpty)
            Padding(padding: const EdgeInsets.only(top: 16), child: Text(item.description)),
          const SizedBox(height: 8),
          _info(context, Icons.sell_outlined, l10n.storeVersion,
              Text(l10n.pluginVersionCommit(item.version, item.shortSha), style: muted)),
          _info(
            context,
            Icons.source_outlined,
            l10n.pluginRepository,
            Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              SelectableText(item.repo, style: muted),
              if (item.repo.startsWith('https://github.com/'))
                TextButton.icon(
                  key: const Key('store-open-repo'),
                  style: TextButton.styleFrom(padding: EdgeInsets.zero),
                  onPressed: () => open(Uri.parse(item.repo)),
                  icon: const Icon(Icons.open_in_new, size: 18),
                  label: Text(l10n.storeOpenRepo),
                ),
            ]),
          ),
          _details(context),
          if (item.tags.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Wrap(spacing: 6, runSpacing: 6, children: [for (final t in item.tags) Chip(label: Text(t))]),
            ),
        ],
      ),
    );
  }
}
