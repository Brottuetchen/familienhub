import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../models/common.dart';
import '../../models/documents.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';
import '../../l10n/l10n.dart';

final _deadlinesProvider = FutureProvider.autoDispose((ref) => ref.watch(apiClientProvider).paperlessDeadlines());
final _recentProvider = FutureProvider.autoDispose((ref) => ref.watch(apiClientProvider).paperlessRecent());

/// Dokumente aus Paperless mit dem eigenen Zugang: Fristen, Suche (per Enter), neueste.
class DocumentsScreen extends ConsumerStatefulWidget {
  const DocumentsScreen({super.key});

  @override
  ConsumerState<DocumentsScreen> createState() => _DocumentsScreenState();
}

class _DocumentsScreenState extends ConsumerState<DocumentsScreen> {
  final _query = TextEditingController();
  PaperlessList? _results;
  bool _searching = false;

  @override
  void dispose() {
    _query.dispose();
    super.dispose();
  }

  Future<void> _search() async {
    final q = _query.text.trim();
    if (q.length < 2) {
      setState(() => _results = null);
      return;
    }
    setState(() => _searching = true);
    try {
      final r = await ref.read(apiClientProvider).paperlessSearch(q);
      if (mounted) setState(() => _results = r);
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _searching = false);
    }
  }

  Future<void> _refresh() async {
    ref.invalidate(_deadlinesProvider);
    ref.invalidate(_recentProvider);
    await ref.read(_recentProvider.future);
  }

  Future<void> _remind(PaperlessDoc d) async {
    try {
      final created = await ref.read(apiClientProvider).paperlessRemind(d.id);
      if (mounted) showInfo(context, created ? l10n.reminderCreatedOn(localDate('d.M.').format(d.deadline!)) : l10n.reminderExists);
    } catch (e) {
      if (mounted) showError(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final recent = ref.watch(_recentProvider);
    final needsAccount = recent.valueOrNull?.needsAccount ?? false;
    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.documents),
        actions: [
          if (!needsAccount && recent.hasValue)
            PopupMenuButton<String>(
              onSelected: (_) async {
                await ref.read(apiClientProvider).disconnectPaperless();
                await _refresh();
              },
              itemBuilder: (_) => [PopupMenuItem(value: 'disconnect', child: Text(l10n.disconnectPaperless))],
            ),
        ],
      ),
      body: HubRefresh(
        onRefresh: _refresh,
        child: recent.when(
          loading: () => const Center(child: HubLoader()),
          error: (e, _) => ErrorView(error: e, onRetry: _refresh),
          data: (list) {
            if (list.status == 'not_configured') {
              return ListView(children: [EmptyHint(icon: Icons.description_outlined, text: l10n.paperlessNotSetUp)]);
            }
            if (list.needsAccount) return _ConnectView(failed: list.status == 'auth_failed', onConnected: _refresh);
            final shown = _results ?? list;
            return ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.only(bottom: 24),
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
                  child: TextField(
                    key: const Key('documents-search'),
                    controller: _query,
                    textInputAction: TextInputAction.search,
                    onSubmitted: (_) => _search(), // Suche nur per Enter, nicht bei jedem Buchstaben
                    decoration: InputDecoration(
                      prefixIcon: const Icon(Icons.search),
                      hintText: l10n.searchDocuments,
                      suffixIcon: _results == null
                          ? null
                          : IconButton(tooltip: l10n.clearSearch, icon: const Icon(Icons.close),
                              onPressed: () => setState(() { _query.clear(); _results = null; })),
                    ),
                  ),
                ),
                if (_searching) const Center(child: HubLoader(size: 32)),
                if (list.status == 'unavailable') SourceBanner(source: 'Paperless', status: SourceStatus.unavailable, error: list.error),
                if (_results == null) _Deadlines(onRemind: _remind),
                _SectionTitle(_results == null ? l10n.newest : l10n.hitsCount(shown.items.length)),
                if (shown.items.isEmpty) EmptyHint(icon: Icons.search_off, text: l10n.noDocuments),
                for (final d in shown.items) _DocTile(doc: d),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  final String text;
  const _SectionTitle(this.text);
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
        child: Text(text, style: Theme.of(context).textTheme.titleSmall?.copyWith(color: Theme.of(context).colorScheme.primary)),
      );
}

class _Deadlines extends ConsumerWidget {
  final void Function(PaperlessDoc) onRemind;
  const _Deadlines({required this.onRemind});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final list = ref.watch(_deadlinesProvider).valueOrNull;
    if (list == null || list.items.isEmpty) return const SizedBox.shrink();
    final theme = Theme.of(context);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      _SectionTitle(l10n.deadlines),
      for (final d in list.items)
        ListTile(
          key: ValueKey('deadline-${d.id}'),
          leading: Container(
            width: 48,
            height: 48,
            padding: const EdgeInsets.all(4),
            decoration: BoxDecoration(color: theme.colorScheme.errorContainer, borderRadius: BorderRadius.circular(10)),
            // FittedBox: auch bei großer Systemschrift kein Überlauf in der 48-px-Kachel
            child: FittedBox(
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                Text(localDate('d.').format(d.deadline!), style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800, height: 1.1)),
                Text(localDate('MMM').format(d.deadline!), style: theme.textTheme.labelSmall?.copyWith(height: 1.1)),
              ]),
            ),
          ),
          title: Text(d.task ?? d.title),
          subtitle: Text([d.correspondent, d.title].whereType<String>().join(' · '), maxLines: 1, overflow: TextOverflow.ellipsis),
          trailing: IconButton(tooltip: l10n.remind, icon: const Icon(Icons.alarm_add), onPressed: () => onRemind(d)),
          onTap: () => _open(d.url),
        ),
    ]);
  }
}

Future<void> _open(String url) async {
  if (url.isEmpty) return;
  await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
}

class _DocTile extends ConsumerWidget {
  final PaperlessDoc doc;
  const _DocTile({required this.doc});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final meta = [doc.correspondent, if (doc.created != null) localDate('d.M.yyyy').format(doc.created!)]
        .whereType<String>()
        .join(' · ');
    return ListTile(
      key: ValueKey('doc-${doc.id}'),
      leading: ClipRRect(
        borderRadius: BorderRadius.circular(6),
        child: SizedBox(
          width: 40,
          height: 56,
          child: FutureBuilder<Uint8List?>(
            future: doc.thumb.isEmpty ? Future.value(null) : ref.read(apiClientProvider).paperlessThumb(doc.thumb),
            builder: (_, snap) => snap.data == null
                ? ColoredBox(color: theme.colorScheme.surfaceContainerHigh, child: const Icon(Icons.description_outlined, size: 20))
                : Image.memory(snap.data!, fit: BoxFit.cover),
          ),
        ),
      ),
      title: Text(doc.title, maxLines: 2, overflow: TextOverflow.ellipsis),
      subtitle: Text([meta, if (doc.documentType != null) doc.documentType!].where((s) => s.isNotEmpty).join(' · '),
          maxLines: 1, overflow: TextOverflow.ellipsis),
      onTap: () => _open(doc.url),
    );
  }
}

/// Eigenen Paperless-Zugang verbinden: API-Token aus Paperless einfügen.
class _ConnectView extends ConsumerStatefulWidget {
  final bool failed;
  final Future<void> Function() onConnected;
  const _ConnectView({required this.failed, required this.onConnected});

  @override
  ConsumerState<_ConnectView> createState() => _ConnectViewState();
}

class _ConnectViewState extends ConsumerState<_ConnectView> {
  final _token = TextEditingController();
  bool _busy = false;

  @override
  void dispose() {
    _token.dispose();
    super.dispose();
  }

  Future<void> _connect() async {
    if (_token.text.trim().isEmpty) return;
    setState(() => _busy = true);
    try {
      final r = await ref.read(apiClientProvider).connectPaperless(_token.text.trim());
      if (mounted) showInfo(context, l10n.connectedAs(r['username'] ?? l10n.paperlessUser));
      await widget.onConnected();
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListView(padding: const EdgeInsets.all(20), children: [
      Icon(Icons.description_outlined, size: 48, color: theme.colorScheme.primary),
      const SizedBox(height: 12),
      Text(widget.failed ? l10n.paperlessTokenInvalid : l10n.connectPaperless, style: theme.textTheme.titleLarge),
      const SizedBox(height: 8),
      Text(l10n.paperlessExplain),
      const SizedBox(height: 16),
      TextField(
        key: const Key('paperless-token'),
        controller: _token,
        obscureText: true,
        autocorrect: false,
        enableSuggestions: false,
        decoration: InputDecoration(labelText: l10n.paperlessToken),
        onSubmitted: (_) => _connect(),
      ),
      const SizedBox(height: 16),
      FilledButton(
        key: const Key('paperless-connect'),
        onPressed: _busy ? null : _connect,
        child: _busy ? const HubLoader(size: 20) : Text(l10n.connect),
      ),
    ]);
  }
}
