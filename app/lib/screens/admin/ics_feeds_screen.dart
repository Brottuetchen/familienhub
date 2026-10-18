import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../l10n/l10n.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';

typedef IcsFeed = ({String name, String url});

final icsFeedsProvider = FutureProvider.autoDispose<List<IcsFeed>>((ref) => ref.watch(apiClientProvider).icsFeeds());

/// Calendar subscriptions (admin and setup wizard): add with a check, remove. Closes with `true` after changes.
class IcsFeedsScreen extends ConsumerStatefulWidget {
  const IcsFeedsScreen({super.key});

  @override
  ConsumerState<IcsFeedsScreen> createState() => _IcsFeedsScreenState();
}

class _IcsFeedsScreenState extends ConsumerState<IcsFeedsScreen> {
  bool _changed = false;

  Future<void> _save(List<IcsFeed> feeds) async {
    if (await runAction(context, () => ref.read(apiClientProvider).saveIcsFeeds(feeds))) {
      _changed = true;
      ref.invalidate(icsFeedsProvider);
      ref.invalidate(eventsProvider);
    }
  }

  Future<void> _add(List<IcsFeed> current) async {
    final feed = await showDialog<IcsFeed>(context: context, builder: (_) => const _AddFeedDialog());
    if (feed != null && mounted) await _save([...current, feed]);
  }

  Future<void> _remove(List<IcsFeed> current, IcsFeed feed) async {
    final sure = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        content: Text(l10n.icsRemoveQuestion(feed.name)),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: Text(l10n.cancel)),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: Text(l10n.remove)),
        ],
      ),
    );
    if (sure == true && mounted) await _save([for (final f in current) if (f != feed) f]);
  }

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(icsFeedsProvider);
    final muted = TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant);
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) Navigator.pop(context, _changed);
      },
      child: Scaffold(
        appBar: AppBar(title: Text(l10n.icsTitle)),
        floatingActionButton: async.valueOrNull == null
            ? null
            : FloatingActionButton.extended(
                key: const Key('ics-add'),
                onPressed: () => _add(async.value!),
                icon: const Icon(Icons.add),
                label: Text(l10n.icsAdd),
              ),
        body: async.when(
          loading: () => const Center(child: HubLoader()),
          error: (e, _) => ErrorView(error: e, onRetry: () => ref.invalidate(icsFeedsProvider)),
          data: (feeds) => ListView(padding: const EdgeInsets.only(bottom: 96), children: [
            Padding(padding: const EdgeInsets.fromLTRB(16, 12, 16, 8), child: Text(l10n.icsExplain, style: muted)),
            if (feeds.isEmpty) EmptyHint(icon: Icons.event_note_outlined, text: l10n.icsNone),
            for (final f in feeds)
              ListTile(
                key: ValueKey('ics-${f.name}'),
                leading: const Icon(Icons.event_repeat),
                title: Text(f.name),
                subtitle: Text(f.url, maxLines: 1, overflow: TextOverflow.ellipsis),
                trailing: IconButton(
                  tooltip: l10n.remove,
                  icon: const Icon(Icons.delete_outline),
                  onPressed: () => _remove(feeds, f),
                ),
              ),
          ]),
        ),
      ),
    );
  }
}

class _AddFeedDialog extends ConsumerStatefulWidget {
  const _AddFeedDialog();

  @override
  ConsumerState<_AddFeedDialog> createState() => _AddFeedDialogState();
}

class _AddFeedDialogState extends ConsumerState<_AddFeedDialog> {
  final _name = TextEditingController();
  final _url = TextEditingController();
  bool _checking = false;
  Map<String, dynamic>? _result;
  String? _checkedUrl;

  @override
  void dispose() {
    _name.dispose();
    _url.dispose();
    super.dispose();
  }

  bool get _ok => _result?['ok'] == true && _checkedUrl == _url.text.trim();

  Future<void> _check() async {
    final url = _url.text.trim();
    setState(() {
      _checking = true;
      _result = null;
    });
    try {
      final r = await ref.read(apiClientProvider).probeIcs(url);
      if (mounted) {
        setState(() {
          _result = r;
          _checkedUrl = url;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _result = {'ok': false, 'error': errorText(e)};
          _checkedUrl = url;
        });
      }
    } finally {
      if (mounted) setState(() => _checking = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final r = _result;
    final theme = Theme.of(context);
    return AlertDialog(
      title: Text(l10n.icsAdd),
      content: SingleChildScrollView(
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          TextField(key: const Key('ics-name'), controller: _name, autofocus: true, textCapitalization: TextCapitalization.sentences,
              decoration: InputDecoration(labelText: l10n.icsName), onChanged: (_) => setState(() {})),
          const SizedBox(height: 8),
          TextField(key: const Key('ics-url'), controller: _url, keyboardType: TextInputType.url,
              decoration: InputDecoration(labelText: l10n.icsUrl, helperText: l10n.icsUrlHint, helperMaxLines: 2),
              onChanged: (_) => setState(() {})),
          const SizedBox(height: 12),
          Align(
            alignment: Alignment.centerLeft,
            child: OutlinedButton.icon(
              key: const Key('ics-check'),
              onPressed: _checking || _url.text.trim().length < 8 ? null : _check,
              icon: _checking ? const HubLoader.small() : const Icon(Icons.fact_check_outlined),
              label: Text(l10n.icsCheck),
            ),
          ),
          if (r != null) ...[
            const SizedBox(height: 8),
            if (r['ok'] == true) ...[
              Text(l10n.icsFound((r['events'] as num?)?.toInt() ?? 0), key: const Key('ics-result'),
                  style: TextStyle(color: Colors.green.shade700)),
              for (final t in (r['sample'] as List? ?? const [])) Text('• $t', style: theme.textTheme.bodySmall),
            ] else
              Text('${r['error'] ?? ''}', key: const Key('ics-result'), style: TextStyle(color: theme.colorScheme.error)),
          ],
        ]),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: Text(l10n.cancel)),
        FilledButton(
          key: const Key('ics-save'),
          // Only checked links: a wrong address would otherwise just stay empty without anyone noticing
          onPressed: _ok && _name.text.trim().isNotEmpty
              ? () => Navigator.pop(context, (name: _name.text.trim(), url: _url.text.trim()))
              : null,
          child: Text(l10n.add),
        ),
      ],
    );
  }
}
