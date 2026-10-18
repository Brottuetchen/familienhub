import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/account.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';
import '../../l10n/l10n.dart';

class RemindersScreen extends ConsumerWidget {
  const RemindersScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(remindersProvider);
    final format = localDate('EEE, d.M. HH:mm');
    Future<void> refresh() => ref.refresh(remindersProvider.future);

    return Scaffold(
      appBar: AppBar(title: Text(l10n.reminders)),
      floatingActionButton: FloatingActionButton(
        tooltip: l10n.createReminder,
        onPressed: () async {
          final created = await showModalBottomSheet<bool>(
            context: context,
            isScrollControlled: true,
            useSafeArea: true,
            builder: (_) => const _ReminderSheet(),
          );
          if (created == true) {
            ref.invalidate(remindersProvider);
          }
        },
        child: const Icon(Icons.add),
      ),
      body: HubRefresh(
        onRefresh: refresh,
        child: async.when(
          loading: () => const Center(child: HubLoader()),
          error: (e, _) => ErrorView(error: e, onRetry: refresh),
          data: (list) => ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            children: [
              if (list.isEmpty) EmptyHint(icon: Icons.notifications_none, text: l10n.noOpenReminders),
              for (final r in list)
                CheckboxListTile(
                  value: false,
                  controlAffinity: ListTileControlAffinity.leading,
                  title: Text(r.title),
                  subtitle: Text([
                    if (r.onArrival && r.dueAt == null)
                      r.forFamily ? l10n.firstHome : l10n.whenYouGetHome
                    else
                      r.dueAt == null ? l10n.noTime : format.format(r.dueAt!),
                    if (r.recurrence != 'none') reminderRecurrences[r.recurrence] ?? r.recurrence,
                  ].join(' · ')),
                  secondary: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      if (r.forFamily)
                        Tooltip(message: l10n.forWholeFamily, child: Icon(Icons.groups_outlined)),
                      PopupMenuButton<int>(
                        key: ValueKey('snooze-${r.id}'),
                        tooltip: l10n.remindLater,
                        icon: const Icon(Icons.snooze),
                        onSelected: (minutes) async {
                          if (await runAction(context, () => ref.read(apiClientProvider).snoozeReminder(r.id, minutes))) {
                            ref.invalidate(remindersProvider);
                          }
                        },
                        itemBuilder: (_) => [
                          PopupMenuItem(value: 60, child: Text(l10n.in1Hour)),
                          PopupMenuItem(value: 180, child: Text(l10n.in3Hours)),
                          PopupMenuItem(value: _minutesUntilTomorrow8(), child: Text(l10n.tomorrow8)),
                        ],
                      ),
                    ],
                  ),
                  // Familien-Erinnerungen hakt ab Kind ab (Gast nur eigene)
                  onChanged: r.forFamily && !ref.watch(canActProvider) ? null : (_) async {
                    if (await runAction(context, () => ref.read(apiClientProvider).completeReminder(r.id))) {
                      ref.invalidate(remindersProvider);
                    }
                  },
                ),
            ],
          ),
        ),
      ),
    );
  }
}

int _minutesUntilTomorrow8() {
  final now = DateTime.now();
  final t = DateTime(now.year, now.month, now.day + 1, 8);
  return t.difference(now).inMinutes;
}

class _ReminderSheet extends ConsumerStatefulWidget {
  const _ReminderSheet();

  @override
  ConsumerState<_ReminderSheet> createState() => _ReminderSheetState();
}

class _ReminderSheetState extends ConsumerState<_ReminderSheet> {
  final _title = TextEditingController();
  DateTime? _due;
  bool _forFamily = false;
  String _recurrence = 'none';
  bool _onArrival = false;

  @override
  void dispose() {
    _title.dispose();
    super.dispose();
  }

  Future<void> _pick() async {
    final now = DateTime.now();
    final d = await showDatePicker(
      context: context,
      initialDate: _due ?? now,
      firstDate: now.subtract(const Duration(days: 1)),
      lastDate: now.add(const Duration(days: 365 * 3)),
    );
    if (d == null || !mounted) return;
    final t = await showTimePicker(context: context, initialTime: const TimeOfDay(hour: 9, minute: 0));
    if (t == null) return;
    setState(() => _due = DateTime(d.year, d.month, d.day, t.hour, t.minute));
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(20, 20, 20, 20 + MediaQuery.viewInsetsOf(context).bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          TextField(
            controller: _title,
            autofocus: true,
            textCapitalization: TextCapitalization.sentences,
            decoration: InputDecoration(labelText: l10n.remindWhat),
          ),
          const SizedBox(height: 12),
          SegmentedButton<bool>(
            key: const Key('reminder-fire-on'),
            segments: [
              ButtonSegment(value: false, icon: Icon(Icons.schedule), label: Text(l10n.atATime)),
              ButtonSegment(value: true, icon: Icon(Icons.home_outlined), label: Text(l10n.onArrival)),
            ],
            selected: {_onArrival},
            onSelectionChanged: (s) => setState(() => _onArrival = s.first),
          ),
          if (ref.watch(canEditProvider))
          SwitchListTile(
            key: const Key('reminder-family'),
            contentPadding: EdgeInsets.zero,
            title: Text(l10n.forWholeFamily),
            subtitle: Text(_onArrival ? l10n.firstHomeGets : l10n.otherwiseOnlyYou),
            value: _forFamily,
            onChanged: (v) => setState(() => _forFamily = v),
          ),
          DropdownButtonFormField<String>(
            key: const Key('reminder-recurrence'),
            initialValue: _recurrence,
            decoration: InputDecoration(labelText: l10n.repeatVerb),
            items: [
              for (final e in reminderRecurrences.entries) DropdownMenuItem(value: e.key, child: Text(e.value)),
            ],
            onChanged: (v) => setState(() => _recurrence = v ?? 'none'),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              if (!_onArrival)
                TextButton.icon(
                  onPressed: _pick,
                  icon: const Icon(Icons.alarm),
                  label: Text(_due == null ? l10n.time : localDate('EEE, d.M. HH:mm').format(_due!)),
                ),
              const Spacer(),
              FilledButton(
                onPressed: () async {
                  final title = _title.text.trim();
                  if (title.isEmpty) return;
                  if (await runAction(context, () => ref.read(apiClientProvider).createReminder(title, _due,
                      forFamily: _forFamily, recurrence: _recurrence, onArrival: _onArrival))) {
                    if (context.mounted) Navigator.pop(context, true);
                  }
                },
                child: Text(l10n.create),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
