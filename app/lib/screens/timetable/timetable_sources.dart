part of 'timetable_screen.dart';

/// Which plugin provides the timetable of each child, and who the child is in the plugin's system.
class _SourcesSheet extends ConsumerStatefulWidget {
  const _SourcesSheet();

  @override
  ConsumerState<_SourcesSheet> createState() => _SourcesSheetState();
}


class _SourcesSheetState extends ConsumerState<_SourcesSheet> {
  final _plugin = <int, String?>{};
  final _person = <int, String?>{};
  final _fields = <int, TextEditingController>{};
  bool _filled = false;
  bool _busy = false;

  @override
  void dispose() {
    for (final c in _fields.values) {
      c.dispose();
    }
    super.dispose();
  }

  void _fill(TimetableSources sources) {
    if (_filled) return;
    _filled = true;
    for (final c in sources.children) {
      _plugin[c.childId] = sources.plugins.any((p) => p.id == c.pluginId) ? c.pluginId : null;
      _person[c.childId] = c.personId;
      _fields[c.childId] = TextEditingController(text: c.personId ?? '');
    }
  }

  Future<void> _save(TimetableSources sources) async {
    final api = ref.read(apiClientProvider);
    setState(() => _busy = true);
    final body = [
      for (final c in sources.children)
        {
          'child_id': c.childId,
          'plugin_id': _plugin[c.childId],
          'person_id': _plugin[c.childId] == null
              ? null
              : (sources.plugins.firstWhere((p) => p.id == _plugin[c.childId]).peopleKnown
                  ? _person[c.childId]
                  : _fields[c.childId]!.text.trim()),
        },
    ];
    final ok = await runAction(context, () => api.saveTimetableSources(body));
    if (!mounted) return;
    if (ok) {
      Navigator.pop(context, true);
    } else {
      setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final muted = theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    final async = ref.watch(timetableSourcesProvider);
    return SingleChildScrollView(
      padding: EdgeInsets.fromLTRB(16, 16, 16, 16 + MediaQuery.of(context).viewInsets.bottom),
      child: async.when(
        loading: () => const Padding(padding: EdgeInsets.all(32), child: Center(child: HubLoader())),
        error: (e, _) => ErrorView(error: e, onRetry: () => ref.invalidate(timetableSourcesProvider)),
        data: (sources) {
          _fill(sources);
          return Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Text(l10n.timetableSources, style: theme.textTheme.titleLarge),
            const SizedBox(height: 8),
            Text(sources.plugins.isEmpty ? l10n.timetableSourcesNone : l10n.timetableSourcesHelp, style: muted),
            if (sources.plugins.isNotEmpty)
              for (final c in sources.children) ...[
                const SizedBox(height: 16),
                Text(c.name, style: theme.textTheme.titleMedium),
                const SizedBox(height: 4),
                DropdownButtonFormField<String?>(
                  key: Key('timetable-source-plugin-${c.childId}'),
                  initialValue: _plugin[c.childId],
                  isExpanded: true,
                  decoration: InputDecoration(labelText: l10n.timetableSourcePlugin),
                  items: [
                    DropdownMenuItem<String?>(value: null, child: Text(l10n.timetableSourceOwn)),
                    for (final p in sources.plugins) DropdownMenuItem<String?>(value: p.id, child: Text(p.name)),
                  ],
                  onChanged: (v) => setState(() {
                    if (v != _plugin[c.childId]) _person[c.childId] = null; // a person belongs to one plugin
                    _plugin[c.childId] = v;
                  }),
                ),
                if (_plugin[c.childId] != null) ...[
                  const SizedBox(height: 8),
                  _personField(sources, c),
                ],
              ],
            const SizedBox(height: 12),
            Wrap(alignment: WrapAlignment.end, spacing: 8, runSpacing: 8, children: [
              TextButton(onPressed: _busy ? null : () => Navigator.pop(context), child: Text(l10n.cancel)),
              if (sources.plugins.isNotEmpty)
                FilledButton(
                  key: const Key('timetable-sources-save'),
                  onPressed: _busy ? null : () => _save(sources),
                  child: Text(l10n.save),
                ),
            ]),
          ]);
        },
      ),
    );
  }

  Widget _personField(TimetableSources sources, TimetableChildSource c) {
    final plugin = sources.plugins.firstWhere((p) => p.id == _plugin[c.childId]);
    if (plugin.peopleKnown && plugin.people.isNotEmpty) {
      final current = plugin.people.any((x) => x.id == _person[c.childId]) ? _person[c.childId] : null;
      return DropdownButtonFormField<String?>(
        key: Key('timetable-source-person-${c.childId}-${plugin.id}'),
        initialValue: current,
        isExpanded: true,
        decoration: InputDecoration(labelText: l10n.timetableSourcePerson),
        items: [for (final x in plugin.people) DropdownMenuItem<String?>(value: x.id, child: Text(x.name))],
        onChanged: (v) => setState(() => _person[c.childId] = v),
      );
    }
    return TextField(
      key: Key('timetable-source-id-${c.childId}'),
      controller: _fields[c.childId],
      maxLength: 200,
      decoration: InputDecoration(labelText: l10n.timetableSourceIdentifier),
    );
  }
}
