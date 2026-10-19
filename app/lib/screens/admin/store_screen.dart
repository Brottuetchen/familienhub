import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../l10n/l10n.dart';
import '../../models/store.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';
import 'store_detail_screen.dart';
import 'store_sources_screen.dart';

/// Entries of all store sources (`GET /api/admin/store`).
final storeProvider = FutureProvider.autoDispose<StoreListing>((ref) => ref.watch(apiClientProvider).storeListing());

enum StoreFilter { all, themes, plugins }

/// Entries matching the type filter and the search text (name, summary, description, author, tags).
List<StoreItem> filterStore(List<StoreItem> items, StoreFilter filter, String query) {
  final q = query.trim().toLowerCase();
  return [
    for (final i in items)
      if ((filter == StoreFilter.all || (filter == StoreFilter.plugins) == i.isPlugin) &&
          (q.isEmpty ||
              [i.name, i.summary, i.description, i.author, ...i.tags].any((t) => t.toLowerCase().contains(q))))
        i
  ];
}

/// Administration → Store: install plugins and themes from the official index and from custom sources.
class StoreScreen extends ConsumerStatefulWidget {
  const StoreScreen({super.key});

  @override
  ConsumerState<StoreScreen> createState() => _StoreScreenState();
}

class _StoreScreenState extends ConsumerState<StoreScreen> {
  final _search = TextEditingController();
  StoreFilter _filter = StoreFilter.all;

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _refresh() async {
    try {
      await ref.read(apiClientProvider).storeListing(refresh: true); // fills the server's cache with fresh data
    } catch (_) {
      // the provider below shows the error
    }
    ref.invalidate(storeProvider);
    await ref.read(storeProvider.future).then((_) {}, onError: (Object _) {});
  }

  Future<void> _open(StoreItem item) async {
    final installer = ref.read(storeProvider).valueOrNull?.installerEnabled ?? true;
    await Navigator.of(context)
        .push(MaterialPageRoute(builder: (_) => StoreDetailScreen(item: item, installerEnabled: installer)));
    ref.invalidate(storeProvider);
  }

  Future<void> _sources() async {
    await Navigator.of(context).push(MaterialPageRoute(builder: (_) => const StoreSourcesScreen()));
    ref.invalidate(storeProvider);
  }

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(storeProvider);
    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.store),
        actions: [
          IconButton(
            key: const Key('store-sources'),
            tooltip: l10n.storeSources,
            icon: const Icon(Icons.source_outlined),
            onPressed: _sources,
          ),
        ],
      ),
      body: HubRefresh(
        onRefresh: _refresh,
        child: async.when(
          loading: () => const Center(child: HubLoader()),
          error: (e, _) => ErrorView(error: e, onRetry: () => ref.invalidate(storeProvider)),
          data: _body,
        ),
      ),
    );
  }

  Widget _body(StoreListing listing) {
    final shown = filterStore(listing.items, _filter, _search.text);
    return LayoutBuilder(builder: (context, box) {
      final columns = (box.maxWidth / 340).floor().clamp(1, 4);
      final rows = <List<StoreItem>>[
        for (var i = 0; i < shown.length; i += columns) shown.sublist(i, (i + columns).clamp(0, shown.length)),
      ];
      return CustomScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        slivers: [
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
            sliver: SliverList.list(children: [
              for (final s in listing.sources)
                if (!s.ok || s.stale) _SourceStatus(source: s),
              TextField(
                key: const Key('store-search'),
                controller: _search,
                decoration: InputDecoration(
                  prefixIcon: const Icon(Icons.search),
                  labelText: l10n.search,
                  hintText: l10n.storeSearchHint,
                  suffixIcon: _search.text.isEmpty
                      ? null
                      : IconButton(
                          icon: const Icon(Icons.clear),
                          tooltip: l10n.cancel,
                          onPressed: () => setState(_search.clear),
                        ),
                ),
                onChanged: (_) => setState(() {}),
              ),
              const SizedBox(height: 8),
              Wrap(spacing: 8, runSpacing: 4, children: [
                for (final (f, label) in [
                  (StoreFilter.all, l10n.storeFilterAll),
                  (StoreFilter.themes, l10n.storeFilterThemes),
                  (StoreFilter.plugins, l10n.storeFilterPlugins),
                ])
                  ChoiceChip(
                    key: Key('store-filter-${f.name}'),
                    label: Text(label),
                    selected: _filter == f,
                    onSelected: (_) => setState(() => _filter = f),
                  ),
              ]),
              const SizedBox(height: 8),
              if (shown.isEmpty)
                Padding(
                  key: const Key('store-empty'),
                  padding: const EdgeInsets.symmetric(vertical: 48),
                  child: Text(
                    listing.items.isEmpty ? l10n.storeEmpty : l10n.storeNoMatches,
                    textAlign: TextAlign.center,
                  ),
                ),
            ]),
          ),
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(12, 0, 12, 24),
            sliver: SliverList.builder(
              itemCount: rows.length,
              itemBuilder: (context, r) => Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  for (var c = 0; c < columns; c++)
                    Expanded(
                      child: c < rows[r].length
                          ? _StoreCard(item: rows[r][c], onTap: () => _open(rows[r][c]))
                          : const SizedBox.shrink(),
                    ),
                ],
              ),
            ),
          ),
        ],
      );
    });
  }
}

/// Soft status of a source that could not be read: the store still works with the others.
class _SourceStatus extends StatelessWidget {
  final StoreSource source;
  const _SourceStatus({required this.source});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final name = source.verified ? l10n.storeOfficial : source.name;
    final text = source.stale
        ? l10n.storeSourceStale(name)
        : source.status == 'unreachable'
            ? l10n.storeSourceUnreachable(name)
            : l10n.storeSourceInvalid(name);
    return Container(
      key: Key('store-status-${source.id}'),
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Icon(Icons.cloud_off_outlined, color: scheme.onSurfaceVariant),
        const SizedBox(width: 10),
        Expanded(child: Text(text)),
      ]),
    );
  }
}

/// Small label: type, reviewed / not reviewed, install state.
class StoreBadge extends StatelessWidget {
  final String label;
  final IconData? icon;
  final Color color;
  const StoreBadge({super.key, required this.label, required this.color, this.icon});

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.14),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: color.withValues(alpha: 0.5)),
        ),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          if (icon != null) ...[Icon(icon, size: 14, color: color), const SizedBox(width: 4)],
          Flexible(child: Text(label, style: Theme.of(context).textTheme.labelSmall?.copyWith(color: color))),
        ]),
      );
}

List<Widget> storeBadges(BuildContext context, StoreItem item) {
  final scheme = Theme.of(context).colorScheme;
  return [
    StoreBadge(
      label: item.isPlugin ? l10n.storeTypePlugin : l10n.storeTypeTheme,
      icon: item.isPlugin ? Icons.extension_outlined : Icons.palette_outlined,
      color: scheme.primary,
    ),
    if (item.verified)
      StoreBadge(key: const Key('store-badge-verified'), label: l10n.storeVerified, icon: Icons.verified, color: Colors.green)
    else
      StoreBadge(
          key: const Key('store-badge-unverified'),
          label: l10n.storeUnverified,
          icon: Icons.warning_amber_rounded,
          color: Colors.orange),
    if (item.state == StoreState.update)
      StoreBadge(key: const Key('store-badge-update'), label: l10n.storeUpdateAvailable, icon: Icons.upgrade, color: scheme.tertiary)
    else if (item.state == StoreState.installed)
      StoreBadge(label: l10n.storeInstalled, icon: Icons.check, color: scheme.secondary),
  ];
}

/// First screenshot of an entry, loaded through the hub; a placeholder while loading or without one.
class StoreScreenshot extends ConsumerWidget {
  final String? path;
  final IconData placeholder;
  final BoxFit fit;
  const StoreScreenshot({super.key, required this.path, required this.placeholder, this.fit = BoxFit.cover});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scheme = Theme.of(context).colorScheme;
    final fallback = ColoredBox(
      color: scheme.surfaceContainerHighest,
      child: Center(child: Icon(placeholder, size: 40, color: scheme.onSurfaceVariant)),
    );
    final p = path;
    if (p == null) return fallback;
    return FutureBuilder<Uint8List?>(
      future: ref.read(apiClientProvider).storeScreenshot(p),
      builder: (context, snap) {
        final bytes = snap.data;
        if (bytes == null) return fallback;
        return Image.memory(bytes, fit: fit, errorBuilder: (_, __, ___) => fallback);
      },
    );
  }
}

class _StoreCard extends StatelessWidget {
  final StoreItem item;
  final VoidCallback onTap;
  const _StoreCard({required this.item, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final muted = TextStyle(color: theme.colorScheme.onSurfaceVariant);
    return Card(
      key: Key('store-item-${item.key}'),
      clipBehavior: Clip.antiAlias,
      margin: const EdgeInsets.all(4),
      child: InkWell(
        onTap: onTap,
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          AspectRatio(
            aspectRatio: 16 / 9,
            child: StoreScreenshot(
              path: item.screenshots.isEmpty ? null : item.screenshots.first,
              placeholder: item.isPlugin ? Icons.extension_outlined : Icons.palette_outlined,
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 10, 12, 12),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(item.name, style: theme.textTheme.titleMedium, maxLines: 2, overflow: TextOverflow.ellipsis),
              if (item.author.isNotEmpty)
                Text(l10n.pluginBy(item.author), style: muted, maxLines: 1, overflow: TextOverflow.ellipsis),
              if (item.summary.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(top: 6),
                  child: Text(item.summary, maxLines: 3, overflow: TextOverflow.ellipsis),
                ),
              const SizedBox(height: 8),
              Wrap(spacing: 6, runSpacing: 6, children: storeBadges(context, item)),
            ]),
          ),
        ]),
      ),
    );
  }
}
