import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/account.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';
import '../../l10n/l10n.dart';

final apiTokensProvider = FutureProvider.autoDispose<List<ApiTokenInfo>>(
    (ref) => ref.watch(apiClientProvider).apiTokens());

/// Persönliche Schlüssel für Assistenten (z. B. Sprachassistent). Ein Schlüssel handelt nur als du.
class ApiTokensScreen extends ConsumerWidget {
  const ApiTokensScreen({super.key});

  Future<void> _create(BuildContext context, WidgetRef ref) async {
    final choice = await showDialog<_NewKey>(context: context, builder: (_) => const _NameDialog());
    if (choice == null || choice.name.isEmpty || !context.mounted) return;
    final name = choice.name;
    // Take everything we need from `ref` before the first await: the screen may be gone when the answer arrives.
    final api = ref.read(apiClientProvider);
    final container = ProviderScope.containerOf(context, listen: false);
    try {
      final created = await api.createApiToken(
        name,
        // Default is least privilege (voice endpoints only); full access is an explicit choice.
        scopes: choice.scopes,
      );
      container.invalidate(apiTokensProvider);
      if (!context.mounted) return;
      final plain = created.token;
      if (plain == null || plain.isEmpty) {
        // The key exists on the server but its plaintext did not arrive: tell the user instead of crashing.
        showInfo(context, l10n.tokenNotReturned);
        return;
      }
      await showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (ctx) => AlertDialog(
          title: Text(l10n.keyFor(created.name)),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(l10n.tokenShownOnce),
              const SizedBox(height: 12),
              SelectableText(plain, key: const Key('new-token'), style: const TextStyle(fontFamily: 'monospace')),
            ],
          ),
          actions: [
            TextButton.icon(
              icon: const Icon(Icons.copy),
              label: Text(l10n.copy),
              onPressed: () {
                Clipboard.setData(ClipboardData(text: plain));
                showInfo(ctx, l10n.copied);
              },
            ),
            FilledButton(onPressed: () => Navigator.pop(ctx), child: Text(l10n.finished)),
          ],
        ),
      );
    } catch (e) {
      if (context.mounted) showError(context, e);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(apiTokensProvider);
    final fmt = localDate('d.M.yyyy HH:mm');
    return Scaffold(
      appBar: AppBar(title: Text(l10n.assistantAccess)),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _create(context, ref),
        icon: const Icon(Icons.key),
        label: Text(l10n.newAccess),
      ),
      body: async.when(
        loading: () => const Center(child: HubLoader()),
        error: (e, _) => ErrorView(error: e, onRetry: () => ref.invalidate(apiTokensProvider)),
        data: (tokens) => ListView(
          children: [
            Padding(
              padding: EdgeInsets.all(16),
              child: Text(l10n.assistantAccessExplain),
            ),
            if (tokens.isEmpty) EmptyHint(icon: Icons.key_off, text: l10n.noAccessYet),
            for (final t in tokens)
              ListTile(
                leading: const Icon(Icons.key),
                title: Text(t.name),
                subtitle: Text([
                  '${t.hint}…',
                  _presetLabel(t),
                  if (t.lastUsedAt != null) l10n.lastUsed(fmt.format(t.lastUsedAt!)) else l10n.neverUsed,
                ].join(' · ')),
                onTap: t.preset == 'custom' ? () => _showScopes(context, t) : null,
                trailing: IconButton(
                  tooltip: l10n.revoke,
                  icon: const Icon(Icons.delete_outline),
                  onPressed: () async {
                    if (await runAction(context, () => ref.read(apiClientProvider).revokeApiToken(t.id))) {
                      ref.invalidate(apiTokensProvider);
                    }
                  },
                ),
              ),
          ],
        ),
      ),
    );
  }
}

String _areaName(String a) => switch (a) {
      'today' => l10n.areaKeyToday,
      'tasks' => l10n.areaKeyTasks,
      'shopping' => l10n.areaKeyShopping,
      'calendar' => l10n.areaKeyCalendar,
      'meals' => l10n.areaKeyMeals,
      'reminders' => l10n.areaKeyReminders,
      'notifications' => l10n.areaKeyNotifications,
      'documents' => l10n.areaKeyDocuments,
      'books' => l10n.areaKeyBooks,
      _ => l10n.areaKeyMedia,
    };

String _presetLabel(ApiTokenInfo t) => switch (t.preset) {
      'full' => l10n.accessFull,
      'voice' => l10n.accessVoice,
      'read' => l10n.accessReadOnly,
      _ => l10n.accessCustomSummary(t.apiAreas.values.where((v) => v.read || v.write).length.toString()),
    };

void _showScopes(BuildContext context, ApiTokenInfo t) {
  showDialog<void>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text(l10n.accessScopesTitle),
      content: SingleChildScrollView(
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          for (final e in t.apiAreas.entries)
            if (e.value.read || e.value.write)
              Text('${_areaName(e.key)}: ${[if (e.value.read) l10n.accessCanRead, if (e.value.write) l10n.accessCanWrite].join(' + ')}'),
        ]),
      ),
      actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: Text(l10n.finished))],
    ),
  );
}

/// Result of the create dialog. [scopes] null = full access.
class _NewKey {
  final String name;
  final List<String>? scopes;
  const _NewKey(this.name, this.scopes);
}

/// Asks for the name and the access type of the new key. Owns its controller and accepts only one submit, so a
/// double tap on "Create" cannot pop the (already closing) route twice.
class _NameDialog extends StatefulWidget {
  const _NameDialog();

  @override
  State<_NameDialog> createState() => _NameDialogState();
}

class _NameDialogState extends State<_NameDialog> {
  final _ctrl = TextEditingController(text: l10n.voiceAssistant);
  bool _done = false;
  String _type = 'voice'; // voice | read | full | custom
  final _read = <String>{};
  final _write = <String>{};

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  void _close([_NewKey? result]) {
    if (_done) return;
    _done = true;
    Navigator.pop(context, result);
  }

  List<String>? get _scopes => switch (_type) {
        'full' => null,
        'read' => const ['read'],
        'custom' => [
            for (final a in apiKeyAreas) ...[
              if (_read.contains(a) || _write.contains(a)) 'api:$a:read',
              if (_write.contains(a)) 'api:$a:write',
            ]
          ],
        _ => const ['voice'],
      };

  String get _hint => switch (_type) {
        'full' => l10n.accessFullWarning,
        'read' => l10n.accessReadHint,
        'custom' => l10n.accessCustomHint,
        _ => l10n.accessVoiceHint,
      };

  Widget _chip(String type, String label) => ChoiceChip(
        key: Key('access-$type'),
        label: Text(label),
        selected: _type == type,
        onSelected: (_) => setState(() => _type = type),
      );

  @override
  Widget build(BuildContext context) {
    final canCreate = _type != 'custom' || _scopes!.isNotEmpty;
    return AlertDialog(
      title: Text(l10n.newAccess),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            TextField(
              controller: _ctrl,
              autofocus: true,
              decoration: InputDecoration(labelText: l10n.whatFor, helperText: l10n.egVoiceAssistant),
            ),
            const SizedBox(height: 16),
            Wrap(spacing: 8, children: [
              _chip('voice', l10n.accessVoice),
              _chip('read', l10n.accessReadOnly),
              _chip('full', l10n.accessFull),
              _chip('custom', l10n.accessCustom),
            ]),
            const SizedBox(height: 8),
            Text(_hint, key: const Key('access-type-hint'), style: Theme.of(context).textTheme.bodySmall),
            if (_type == 'custom') ...[
              const SizedBox(height: 8),
              for (final a in apiKeyAreas)
                Row(children: [
                  Expanded(child: Text(_areaName(a))),
                  Text(l10n.accessCanRead, style: Theme.of(context).textTheme.bodySmall),
                  Checkbox(
                    key: Key('read-$a'),
                    value: _read.contains(a) || _write.contains(a),
                    onChanged: (v) => setState(() {
                      if (v == true) {
                        _read.add(a);
                      } else {
                        _read.remove(a);
                        _write.remove(a);
                      }
                    }),
                  ),
                  Text(l10n.accessCanWrite, style: Theme.of(context).textTheme.bodySmall),
                  Checkbox(
                    key: Key('write-$a'),
                    value: _write.contains(a),
                    onChanged: (v) => setState(() {
                      if (v == true) {
                        _write.add(a);
                        _read.add(a);
                      } else {
                        _write.remove(a);
                      }
                    }),
                  ),
                ]),
              if (_write.isNotEmpty)
                Text(l10n.accessWriteWarning, key: const Key('write-warning'), style: Theme.of(context).textTheme.bodySmall),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(onPressed: _close, child: Text(l10n.cancel)),
        FilledButton(onPressed: canCreate ? () => _close(_NewKey(_ctrl.text.trim(), _scopes)) : null, child: Text(l10n.create)),
      ],
    );
  }
}
