import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../l10n/l10n.dart';
import '../../models/store.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';
import 'store_screen.dart';

/// Store → Sources: the official index (reviewed) and custom GitHub repositories (not reviewed).
class StoreSourcesScreen extends ConsumerWidget {
  const StoreSourcesScreen({super.key});

  Future<void> _add(BuildContext context, WidgetRef ref) async {
    final url = await showDialog<String>(context: context, builder: (_) => const _AddSourceDialog());
    if (url == null || !context.mounted) return;
    if (await runAction(context, () => ref.read(apiClientProvider).addStoreSource(url))) {
      ref.invalidate(storeProvider);
      if (context.mounted) showInfo(context, l10n.storeSourceAdded);
    }
  }

  Future<void> _remove(BuildContext context, WidgetRef ref, StoreSource s) async {
    final sure = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(l10n.storeRemoveSource),
        content: Text(l10n.storeRemoveSourceHint(s.name)),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: Text(l10n.cancel)),
          FilledButton(
              key: const Key('store-source-remove-confirm'),
              onPressed: () => Navigator.pop(ctx, true),
              child: Text(l10n.remove)),
        ],
      ),
    );
    if (sure != true || !context.mounted) return;
    if (await runAction(context, () => ref.read(apiClientProvider).removeStoreSource(s.dbId!))) {
      ref.invalidate(storeProvider);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(storeProvider);
    return Scaffold(
      appBar: AppBar(title: Text(l10n.storeSources)),
      floatingActionButton: FloatingActionButton.extended(
        key: const Key('store-source-add'),
        onPressed: () => _add(context, ref),
        icon: const Icon(Icons.add),
        label: Text(l10n.storeAddSource),
      ),
      body: async.when(
        loading: () => const Center(child: HubLoader()),
        error: (e, _) => ErrorView(error: e, onRetry: () => ref.invalidate(storeProvider)),
        data: (listing) => ListView(
          padding: const EdgeInsets.only(bottom: 96),
          children: [
            Padding(padding: const EdgeInsets.all(16), child: Text(l10n.storeSourcesHint)),
            for (final s in listing.sources)
              ListTile(
                key: Key('store-source-${s.id}'),
                leading: Icon(s.verified ? Icons.verified : Icons.warning_amber_rounded,
                    color: s.verified ? Colors.green : Colors.orange),
                title: Text(s.verified ? l10n.storeOfficial : s.name),
                subtitle: Text([
                  s.verified ? l10n.storeVerified : l10n.storeUnverified,
                  if (s.ok) l10n.storeEntries(s.entries),
                  if (!s.ok && s.status == 'unreachable') l10n.storeSourceUnreachable(s.url),
                  if (!s.ok && s.status != 'unreachable') l10n.storeSourceInvalid(s.url),
                  if (s.ok) s.url,
                ].join('\n')),
                isThreeLine: true,
                trailing: s.removable && s.dbId != null
                    ? IconButton(
                        key: Key('store-source-remove-${s.id}'),
                        tooltip: l10n.remove,
                        icon: const Icon(Icons.delete_outline),
                        onPressed: () => _remove(context, ref, s),
                      )
                    : null,
              ),
          ],
        ),
      ),
    );
  }
}

/// GitHub address plus the "not reviewed" warning, which must be acknowledged before adding.
class _AddSourceDialog extends StatefulWidget {
  const _AddSourceDialog();

  @override
  State<_AddSourceDialog> createState() => _AddSourceDialogState();
}

class _AddSourceDialogState extends State<_AddSourceDialog> {
  final _url = TextEditingController();
  bool _understood = false;

  @override
  void dispose() {
    _url.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final ready = _understood && _url.text.trim().isNotEmpty;
    return AlertDialog(
      key: const Key('store-source-dialog'),
      title: Text(l10n.storeAddSource),
      content: SingleChildScrollView(
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          TextField(
            key: const Key('store-source-url'),
            controller: _url,
            keyboardType: TextInputType.url,
            autocorrect: false,
            decoration: InputDecoration(labelText: l10n.githubAddress, hintText: 'https://github.com/name/repo'),
            onChanged: (_) => setState(() {}),
          ),
          const SizedBox(height: 16),
          Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Icon(Icons.warning_amber_rounded, color: Colors.orange),
            const SizedBox(width: 8),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(l10n.storeUnverifiedTitle, style: Theme.of(context).textTheme.titleSmall),
                Text(l10n.storeUnverifiedSourceBody),
              ]),
            ),
          ]),
          CheckboxListTile(
            key: const Key('store-source-understand'),
            contentPadding: EdgeInsets.zero,
            controlAffinity: ListTileControlAffinity.leading,
            value: _understood,
            title: Text(l10n.storeUnderstand),
            onChanged: (v) => setState(() => _understood = v == true),
          ),
        ]),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: Text(l10n.cancel)),
        FilledButton(
          key: const Key('store-source-save'),
          onPressed: ready ? () => Navigator.pop(context, _url.text.trim()) : null,
          child: Text(l10n.add),
        ),
      ],
    );
  }
}
