import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/common.dart';
import '../../models/task.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';
import '../../l10n/l10n.dart';

/// Zuordnung der Nextcloud-Listen: privat, Familie oder ausgeblendet.
class TaskListsScreen extends ConsumerStatefulWidget {
  const TaskListsScreen({super.key});

  @override
  ConsumerState<TaskListsScreen> createState() => _TaskListsScreenState();
}

class _TaskListsScreenState extends ConsumerState<TaskListsScreen> {
  SourceResult<TaskListInfo>? _lists;
  final _kinds = <String, String?>{};
  Object? _error;
  bool _saving = false;

  static Map<String, String> get _labels => {'personal': l10n.listPrivate, 'family': l10n.family, 'hidden': l10n.hide};

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _error = null);
    try {
      final lists = await ref.read(apiClientProvider).taskLists();
      if (!mounted) return;
      setState(() {
        _lists = lists;
        _kinds
          ..clear()
          ..addAll({for (final l in lists.items) l.caldavUrl: l.kind});
      });
    } catch (e) {
      if (mounted) setState(() => _error = e);
    }
  }

  Future<void> _save() async {
    final me = ref.read(sessionProvider).user;
    final lists = [
      for (final l in _lists!.items)
        TaskListInfo(
          caldavUrl: l.caldavUrl,
          displayName: l.displayName,
          kind: _kinds[l.caldavUrl],
          ownerUserId: _kinds[l.caldavUrl] == 'personal' ? (l.ownerUserId ?? me?.id) : l.ownerUserId,
        ),
    ];
    setState(() => _saving = true);
    final ok = await runAction(context, () => ref.read(apiClientProvider).saveTaskLists(lists));
    if (!mounted) return;
    setState(() => _saving = false);
    if (ok) {
      showInfo(context, l10n.saved);
      Navigator.pop(context);
    }
  }

  @override
  Widget build(BuildContext context) {
    final lists = _lists;
    return Scaffold(
      appBar: AppBar(title: Text(l10n.taskLists)),
      body: _error != null
          ? ErrorView(error: _error!, onRetry: _load)
          : lists == null
              ? const Center(child: HubLoader())
              : ListView(
                  children: [
                    SourceBanner(source: 'Nextcloud', status: lists.status, error: lists.error),
                    Padding(
                      padding: EdgeInsets.all(16),
                      child: Text(l10n.taskListsExplain),
                    ),
                    for (final l in lists.items)
                      ListTile(
                        title: Text(l.displayName),
                        trailing: DropdownButton<String?>(
                          value: _kinds[l.caldavUrl],
                          hint: const Text('–'),
                          items: [
                            for (final e in _labels.entries)
                              DropdownMenuItem(value: e.key, child: Text(e.value)),
                          ],
                          onChanged: (v) => setState(() => _kinds[l.caldavUrl] = v),
                        ),
                      ),
                    Padding(
                      padding: const EdgeInsets.all(16),
                      child: FilledButton(
                        onPressed: _saving || !lists.isOk ? null : _save,
                        child: Text(l10n.save),
                      ),
                    ),
                  ],
                ),
    );
  }
}
