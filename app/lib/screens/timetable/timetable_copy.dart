part of 'timetable_screen.dart';

class _CopyDayDialog extends StatefulWidget {
  final int from;
  const _CopyDayDialog({required this.from});

  @override
  State<_CopyDayDialog> createState() => _CopyDayDialogState();
}


class _CopyDayDialogState extends State<_CopyDayDialog> {
  final _picked = <int>{};

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(l10n.timetableCopyDayTo(_dayName(widget.from))),
      content: SingleChildScrollView(
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Wrap(spacing: 8, runSpacing: 4, children: [
            for (var d = 0; d < 7; d++)
              if (d != widget.from)
                FilterChip(
                  key: Key('timetable-copy-to-$d'),
                  label: Text(_dayName(d)),
                  selected: _picked.contains(d),
                  onSelected: (on) => setState(() => on ? _picked.add(d) : _picked.remove(d)),
                ),
          ]),
          const SizedBox(height: 12),
          Text(l10n.timetableCopyReplaces, style: Theme.of(context).textTheme.bodySmall),
        ]),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: Text(l10n.cancel)),
        FilledButton(
          key: const Key('timetable-copy-confirm'),
          onPressed: _picked.isEmpty ? null : () => Navigator.pop(context, _picked.toList()..sort()),
          child: Text(l10n.copy),
        ),
      ],
    );
  }
}
