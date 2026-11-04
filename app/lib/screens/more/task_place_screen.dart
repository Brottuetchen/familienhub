import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/task.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';
import '../../l10n/l10n.dart';

/// Where tasks that others give me land: automatic (derived from the connected accounts) or a chosen place.
/// The section stays empty while the server does not answer (older server, offline).
class TaskPlaceScreen extends ConsumerStatefulWidget {
  const TaskPlaceScreen({super.key});

  @override
  ConsumerState<TaskPlaceScreen> createState() => _TaskPlaceScreenState();
}

class _TaskPlaceScreenState extends ConsumerState<TaskPlaceScreen> {
  bool _busy = false;

  Future<void> _setPlace(String? place) async {
    setState(() => _busy = true);
    try {
      await ref.read(apiClientProvider).setTaskPlace(place);
      ref.invalidate(taskPlaceProvider);
      if (mounted) showInfo(context, l10n.taskPlaceSaved);
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final info = ref.watch(taskPlaceProvider).valueOrNull;
    return Scaffold(
      appBar: AppBar(title: Text(l10n.taskPlaceTitle)),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
        children: [
          if (info != null) ..._section(theme, info),
        ],
      ),
    );
  }

  List<Widget> _section(ThemeData theme, TaskPlaceInfo info) {
    final selected = info.explicit != null && info.options.any((o) => o.id == info.explicit && o.available) ? info.explicit : null;
    return [
      Padding(
        key: const Key('task-place-section'),
        padding: const EdgeInsets.only(bottom: 16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(l10n.taskPlaceHint, style: theme.textTheme.bodySmall),
          RadioGroup<String>(
            groupValue: selected ?? '',
            onChanged: (value) { if (!_busy) _setPlace(value == null || value.isEmpty ? null : value); },
            child: Column(children: [
              RadioListTile<String>(
                key: const Key('task-place-auto'),
                contentPadding: EdgeInsets.zero,
                value: '',
                title: Text(l10n.taskPlaceAuto(info.auto == null ? '' : taskPlaceName(info.auto!))),
              ),
              for (final option in info.options)
                RadioListTile<String>(
                  key: Key('task-place-${option.id}'),
                  contentPadding: EdgeInsets.zero,
                  value: option.id,
                  enabled: option.available,
                  title: Text(taskPlaceName(option.id)),
                ),
            ]),
          ),
        ]),
      ),
    ];
  }
}
