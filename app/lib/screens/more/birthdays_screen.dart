import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/birthday.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';
import '../../l10n/l10n.dart';

/// Days before an entry the hub reminds about it (null = no reminder).
const _remindChoices = <int?>[null, 0, 1, 3, 7, 14, 30];

bool _leap(int y) => (y % 4 == 0 && y % 100 != 0) || y % 400 == 0;

/// 29 February is fine without a year and with a leap year only.
bool validBirthdayDate(int month, int day, int? year) {
  if (month < 1 || month > 12 || day < 1) return false;
  if (month == 2 && day == 29) return year == null || _leap(year);
  return day <= DateTime(2001, month + 1, 0).day;
}

class BirthdaysScreen extends ConsumerWidget {
  const BirthdaysScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(birthdaysProvider);
    final canEdit = ref.watch(canEditProvider);
    final format = localDate('d. MMMM');
    Future<void> refresh() => ref.refresh(birthdaysProvider.future);

    Future<void> openEditor([Birthday? entry]) async {
      final saved = await showModalBottomSheet<bool>(
        context: context,
        isScrollControlled: true,
        useSafeArea: true,
        builder: (_) => BirthdayEditor(entry: entry),
      );
      if (saved == true) ref.invalidate(birthdaysProvider);
    }

    return Scaffold(
      appBar: AppBar(title: Text(l10n.birthdays)),
      floatingActionButton: canEdit
          ? FloatingActionButton(tooltip: l10n.addBirthday, onPressed: openEditor, child: const Icon(Icons.add))
          : null,
      body: HubRefresh(
        onRefresh: refresh,
        child: async.when(
          loading: () => const Center(child: HubLoader()),
          error: (e, _) => ErrorView(error: e, onRetry: refresh),
          data: (list) => ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            children: [
              if (list.isEmpty) EmptyHint(icon: Icons.cake_outlined, text: l10n.birthdaysEmpty),
              for (final b in list)
                ListTile(
                  key: ValueKey('birthday-${b.id}'),
                  leading: Icon(b.isAnniversary ? Icons.favorite_outline : Icons.cake_outlined),
                  title: Text(b.name),
                  subtitle: Text([
                    if (b.nextDate != null) format.format(b.nextDate!),
                    b.whenText,
                    if (b.giftCount != null && b.giftCount! > 0) l10n.giftIdeaCount(b.giftCount!),
                  ].join(' · ')),
                  isThreeLine: true,
                  trailing: canEdit
                      ? IconButton(
                          key: ValueKey('birthday-edit-${b.id}'),
                          tooltip: l10n.editBirthday,
                          icon: const Icon(Icons.edit_outlined),
                          onPressed: () => openEditor(b),
                        )
                      : null,
                  // The person themself gets no gift ideas, not even an empty list
                  onTap: b.isYou
                      ? null
                      : () => showModalBottomSheet<void>(
                            context: context,
                            isScrollControlled: true,
                            useSafeArea: true,
                            builder: (_) => GiftIdeasSheet(birthday: b),
                          ).then((_) => ref.invalidate(birthdaysProvider)),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class BirthdayEditor extends ConsumerStatefulWidget {
  final Birthday? entry;
  const BirthdayEditor({super.key, this.entry});

  @override
  ConsumerState<BirthdayEditor> createState() => _BirthdayEditorState();
}

class _BirthdayEditorState extends ConsumerState<BirthdayEditor> {
  late final _name = TextEditingController(text: widget.entry?.name ?? '');
  late final _year = TextEditingController(text: widget.entry?.year?.toString() ?? '');
  late String _kind = widget.entry?.kind ?? 'birthday';
  late int _month = widget.entry?.month ?? DateTime.now().month;
  late int _day = widget.entry?.day ?? DateTime.now().day;
  late int? _userId = widget.entry?.userId;
  late int? _remind = widget.entry == null ? 7 : widget.entry!.remindDaysBefore;
  String? _error;
  bool _busy = false;

  @override
  void dispose() {
    _name.dispose();
    _year.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final name = _name.text.trim();
    final yearText = _year.text.trim();
    final year = yearText.isEmpty ? null : int.tryParse(yearText);
    if (name.isEmpty) return;
    if ((yearText.isNotEmpty && (year == null || year < 1000 || year > 9999)) || !validBirthdayDate(_month, _day, year)) {
      setState(() => _error = l10n.birthdayInvalidDate);
      return;
    }
    setState(() => _busy = true);
    final ok = await runAction(
      context,
      () => ref.read(apiClientProvider).saveBirthday(
            id: widget.entry?.id,
            name: name,
            kind: _kind,
            month: _month,
            day: _day,
            year: year,
            userId: _userId,
            remindDaysBefore: _remind,
          ),
    );
    if (!mounted) return;
    if (ok) {
      Navigator.pop(context, true);
    } else {
      setState(() => _busy = false);
    }
  }

  Future<void> _delete() async {
    final sure = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(l10n.birthdayDeleteQuestion),
        content: Text(l10n.birthdayDeleteHint),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: Text(l10n.cancel)),
          TextButton(onPressed: () => Navigator.pop(ctx, true), child: Text(l10n.delete)),
        ],
      ),
    );
    if (sure != true || !mounted) return;
    if (await runAction(context, () => ref.read(apiClientProvider).deleteBirthday(widget.entry!.id)) && mounted) {
      Navigator.pop(context, true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final people = ref.watch(peopleProvider).valueOrNull ?? const [];
    final months = localDate('MMMM');
    return SingleChildScrollView(
      padding: EdgeInsets.fromLTRB(20, 20, 20, 20 + MediaQuery.viewInsetsOf(context).bottom),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(widget.entry == null ? l10n.addBirthday : l10n.editBirthday, style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 12),
          TextField(
            key: const Key('birthday-name'),
            controller: _name,
            autofocus: widget.entry == null,
            textCapitalization: TextCapitalization.words,
            decoration: InputDecoration(labelText: l10n.birthdayName),
          ),
          const SizedBox(height: 12),
          SegmentedButton<String>(
            key: const Key('birthday-kind'),
            segments: [
              ButtonSegment(value: 'birthday', icon: const Icon(Icons.cake_outlined), label: Text(l10n.birthdayKindBirthday)),
              ButtonSegment(value: 'anniversary', icon: const Icon(Icons.favorite_outline), label: Text(l10n.birthdayKindAnniversary)),
            ],
            selected: {_kind},
            onSelectionChanged: (s) => setState(() => _kind = s.first),
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 12,
            runSpacing: 12,
            children: [
              SizedBox(
                width: 110,
                child: DropdownButtonFormField<int>(
                  key: const Key('birthday-day'),
                  isExpanded: true,
                  initialValue: _day,
                  decoration: InputDecoration(labelText: l10n.birthdayDay),
                  items: [for (var d = 1; d <= 31; d++) DropdownMenuItem(value: d, child: Text('$d'))],
                  onChanged: (v) => setState(() => _day = v ?? _day),
                ),
              ),
              SizedBox(
                width: 170,
                child: DropdownButtonFormField<int>(
                  key: const Key('birthday-month'),
                  isExpanded: true,
                  initialValue: _month,
                  decoration: InputDecoration(labelText: l10n.birthdayMonth),
                  items: [
                    for (var m = 1; m <= 12; m++)
                      DropdownMenuItem(value: m, child: Text(months.format(DateTime(2001, m)), overflow: TextOverflow.ellipsis)),
                  ],
                  onChanged: (v) => setState(() => _month = v ?? _month),
                ),
              ),
              SizedBox(
                width: 170,
                child: TextField(
                  key: const Key('birthday-year'),
                  controller: _year,
                  keyboardType: TextInputType.number,
                  decoration: InputDecoration(labelText: l10n.birthdayYear),
                ),
              ),
            ],
          ),
          if (_month == 2 && _day == 29)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(l10n.birthdayLeapHint, style: Theme.of(context).textTheme.bodySmall),
            ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ),
          const SizedBox(height: 12),
          DropdownButtonFormField<int?>(
            key: const Key('birthday-remind'),
            isExpanded: true,
            initialValue: _remind,
            decoration: InputDecoration(labelText: l10n.birthdayRemind),
            items: [
              for (final d in _remindChoices)
                DropdownMenuItem(value: d, child: Text(d == null ? l10n.birthdayRemindNone : l10n.birthdayRemindDays(d))),
            ],
            onChanged: (v) => setState(() => _remind = v),
          ),
          const SizedBox(height: 12),
          DropdownButtonFormField<int?>(
            key: const Key('birthday-user'),
            isExpanded: true,
            initialValue: people.any((p) => p.id == _userId) ? _userId : null,
            decoration: InputDecoration(labelText: l10n.birthdayLinkedUser, helperText: l10n.birthdayLinkedHint, helperMaxLines: 3),
            items: [
              DropdownMenuItem(value: null, child: Text(l10n.birthdayNoUser)),
              for (final p in people) DropdownMenuItem(value: p.id, child: Text(p.displayName, overflow: TextOverflow.ellipsis)),
            ],
            onChanged: (v) => setState(() => _userId = v),
          ),
          const SizedBox(height: 16),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            alignment: WrapAlignment.end,
            children: [
              if (widget.entry != null)
                TextButton(key: const Key('birthday-delete'), onPressed: _busy ? null : _delete, child: Text(l10n.delete)),
              FilledButton(key: const Key('birthday-save'), onPressed: _busy ? null : _save, child: Text(l10n.save)),
            ],
          ),
        ],
      ),
    );
  }
}

/// Gift ideas of one entry, visible to the family but never to the person the entry belongs to (the server enforces it).
class GiftIdeasSheet extends ConsumerStatefulWidget {
  final Birthday birthday;
  const GiftIdeasSheet({super.key, required this.birthday});

  @override
  ConsumerState<GiftIdeasSheet> createState() => _GiftIdeasSheetState();
}

class _GiftIdeasSheetState extends ConsumerState<GiftIdeasSheet> {
  final _text = TextEditingController();
  final _link = TextEditingController();
  String? _error;

  @override
  void dispose() {
    _text.dispose();
    _link.dispose();
    super.dispose();
  }

  Future<void> _add() async {
    final text = _text.text.trim();
    final link = _link.text.trim();
    if (text.isEmpty) return;
    if (link.isNotEmpty && !RegExp(r'^https?://', caseSensitive: false).hasMatch(link)) {
      setState(() => _error = l10n.giftIdeaInvalidLink);
      return;
    }
    final api = ref.read(apiClientProvider);
    if (await runAction(context, () => api.addGiftIdea(widget.birthday.id, text, link: link))) {
      _text.clear();
      _link.clear();
      setState(() => _error = null);
      ref.invalidate(giftIdeasProvider(widget.birthday.id));
    }
  }

  @override
  Widget build(BuildContext context) {
    final id = widget.birthday.id;
    final async = ref.watch(giftIdeasProvider(id));
    final canEdit = ref.watch(canEditProvider);
    final me = ref.watch(sessionProvider).user?.id;
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 8),
            child: Text('${l10n.giftIdeas}: ${widget.birthday.name}', style: Theme.of(context).textTheme.titleLarge),
          ),
          Flexible(
            child: async.when(
              loading: () => const Padding(padding: EdgeInsets.all(24), child: Center(child: HubLoader())),
              error: (e, _) => Padding(padding: const EdgeInsets.all(20), child: Text('$e')),
              data: (list) => ListView(
                shrinkWrap: true,
                children: [
                  if (list.isEmpty)
                    Padding(padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8), child: Text(l10n.giftIdeasEmpty)),
                  for (final g in list)
                    CheckboxListTile(
                      key: ValueKey('gift-${g.id}'),
                      value: g.done,
                      controlAffinity: ListTileControlAffinity.leading,
                      title: Text(g.text, style: g.done ? const TextStyle(decoration: TextDecoration.lineThrough) : null),
                      subtitle: g.link == null ? null : Text(g.link!, maxLines: 2, overflow: TextOverflow.ellipsis),
                      secondary: canEdit || g.createdBy == me
                          ? IconButton(
                              key: ValueKey('gift-delete-${g.id}'),
                              tooltip: l10n.delete,
                              icon: const Icon(Icons.delete_outline),
                              onPressed: () async {
                                if (await runAction(context, () => ref.read(apiClientProvider).deleteGiftIdea(id, g.id))) {
                                  ref.invalidate(giftIdeasProvider(id));
                                }
                              },
                            )
                          : null,
                      onChanged: (v) async {
                        if (await runAction(context, () => ref.read(apiClientProvider).setGiftIdeaDone(id, g.id, v ?? false))) {
                          ref.invalidate(giftIdeasProvider(id));
                        }
                      },
                    ),
                ],
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 8, 20, 8),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                TextField(
                  key: const Key('gift-text'),
                  controller: _text,
                  textCapitalization: TextCapitalization.sentences,
                  decoration: InputDecoration(labelText: l10n.giftIdeaText),
                ),
                const SizedBox(height: 8),
                TextField(
                  key: const Key('gift-link'),
                  controller: _link,
                  keyboardType: TextInputType.url,
                  decoration: InputDecoration(labelText: l10n.giftIdeaLink, errorText: _error),
                ),
                const SizedBox(height: 8),
                Align(
                  alignment: Alignment.centerRight,
                  child: FilledButton(key: const Key('gift-add'), onPressed: _add, child: Text(l10n.add)),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
