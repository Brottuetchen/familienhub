import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../core/theme/hub_style.dart';
import '../../models/account.dart';
import '../../models/meals.dart';
import '../../models/shopping.dart';
import '../../models/task.dart';
import '../../models/themes.dart' show hexColor;
import '../../providers/providers.dart';
import '../../widgets/common.dart';
import '../more/notifications_screen.dart';
import '../tasks/habitica_tasks.dart';
import '../tasks/tasks_screen.dart' show taskDueLabel;

/// Filter der Aufgaben auf „Heute“: null = fällig/zugewiesen (wie bisher), sonst eine Ansicht.
final todayTaskFilterProvider = StateProvider<TaskView?>((ref) => null);

Color _personColor(BuildContext context, int id) {
  final style = HubStyle.of(context);
  final scheme = Theme.of(context).colorScheme;
  final palette = style.accents.isNotEmpty ? style.accents : [scheme.primary, scheme.secondary, scheme.tertiary];
  return palette[id.abs() % palette.length];
}

/// Zwei Buchstaben („Co“, „Ca“), damit sich Personen mit gleichem Anfangsbuchstaben unterscheiden.
String initialsOf(String name) {
  final parts = name.trim().split(RegExp(r'\s+')).where((p) => p.isNotEmpty).toList();
  if (parts.isEmpty) return '?';
  if (parts.length >= 2) return (parts[0].characters.first + parts[1].characters.first).toUpperCase();
  final c = parts[0].characters;
  return c.length >= 2 ? c.first.toUpperCase() + c.elementAt(1).toLowerCase() : c.first.toUpperCase();
}

/// Avatar einer Person: Profilbild, sonst zwei Buchstaben in der eigenen (oder Theme-)Farbe.
class PersonAvatar extends ConsumerWidget {
  final String name;
  final int id;
  final double size;
  final String? color; // #RRGGBB aus dem Profil
  final String? imageUrl;
  const PersonAvatar({super.key, required this.name, required this.id, this.size = 28, this.color, this.imageUrl});

  factory PersonAvatar.of(Person p, {double size = 28, Key? key}) =>
      PersonAvatar(key: key, name: p.displayName, id: p.id, size: size, color: p.avatarColor, imageUrl: p.avatarUrl);

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final style = HubStyle.of(context);
    final bg = hexColor(color) ?? _personColor(context, id);
    final on = ThemeData.estimateBrightnessForColor(bg) == Brightness.dark ? Colors.white : Colors.black;
    final border = Border.all(
      color: style.borderWidth >= 2 ? style.border : Theme.of(context).scaffoldBackgroundColor.withValues(alpha: 1),
      width: style.borderWidth >= 2 ? 2 : 1.5,
    );
    final fallback = Center(
      child: Text(initialsOf(name),
          style: TextStyle(color: on, fontWeight: FontWeight.w700, fontSize: size * 0.38, height: 1)),
    );
    if (imageUrl == null) {
      return Tooltip(
        message: name,
        child: Container(
          width: size,
          height: size,
          decoration: BoxDecoration(color: bg, shape: BoxShape.circle, border: border),
          child: fallback,
        ),
      );
    }
    // Mit Foto: Ring in der Profilfarbe, dazwischen ein schmaler Spalt in Hintergrundfarbe
    final ring = (size * 0.07).clamp(2.0, 6.0);
    final gap = (size * 0.035).clamp(1.0, 3.0);
    return Tooltip(
      message: name,
      child: Container(
        key: const Key('avatar-ring'),
        width: size,
        height: size,
        padding: EdgeInsets.all(ring),
        decoration: BoxDecoration(shape: BoxShape.circle, color: bg),
        child: Container(
          padding: EdgeInsets.all(gap),
          decoration: BoxDecoration(shape: BoxShape.circle, color: Theme.of(context).scaffoldBackgroundColor.withValues(alpha: 1)),
          child: ClipOval(
            child: ColoredBox(
              color: bg,
              child: FutureBuilder<Uint8List?>(
                future: ref.read(apiClientProvider).avatarBytes(imageUrl!),
                builder: (context, snap) => snap.data == null
                    ? SizedBox.expand(child: fallback)
                    : Image.memory(snap.data!, fit: BoxFit.cover, width: size, height: size, gaplessPlayback: true),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Großer Kopf: Gruß, Datum, Mitteilungs-Glocke mit Zähler, Avatare der Familie.
class TodayHeader extends ConsumerWidget {
  final String greeting;
  final int unread;
  final Widget? status; // kleines Symbol: aktuell / lädt / offline
  const TodayHeader({super.key, required this.greeting, this.unread = 0, this.status});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final style = HubStyle.of(context);
    final people = ref.watch(peopleProvider).valueOrNull ?? const <Person>[];
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 12, 12, 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(greeting,
                  key: const Key('today-greeting'),
                  style: theme.textTheme.headlineMedium?.copyWith(fontWeight: style.titleWeight, height: 1.1)),
            ),
          ),
          if (status != null) status!,
          IconButton(
            key: const Key('today-bell'),
            tooltip: unread == 0 ? 'Mitteilungen' : '$unread neue Mitteilungen',
            onPressed: () async {
              await Navigator.of(context).push(MaterialPageRoute(builder: (_) => const NotificationsScreen()));
              await ref.read(todayProvider.notifier).refresh();
            },
            icon: Badge(
              isLabelVisible: unread > 0,
              label: Text('$unread'),
              child: const Icon(Icons.notifications_none),
            ),
          ),
          if (people.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 6, right: 4),
              child: SizedBox(
                width: 22.0 * people.take(3).length + 10,
                height: 32,
                child: Stack(
                  children: [
                    for (final (i, p) in people.take(3).indexed)
                      Positioned(left: i * 22.0, child: PersonAvatar.of(p, size: 32)),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// Pillen-Auswahl im Stil des Themes (Verlauf bei Glas, Rahmen bei Neo-Brutalism).
class StylePill extends StatelessWidget {
  final String label;
  final bool selected;
  final VoidCallback onTap;
  const StylePill({super.key, required this.label, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final style = HubStyle.of(context);
    final scheme = Theme.of(context).colorScheme;
    final heavy = style.borderWidth >= 2;
    final fill = selected
        ? (style.bandHeader && style.accents.isNotEmpty ? style.accents.first : scheme.primary)
        : (style.glass ? Colors.white.withValues(alpha: 0.06) : style.surface);
    final textColor = selected
        ? (ThemeData.estimateBrightnessForColor(fill) == Brightness.dark ? Colors.white : Colors.black)
        : scheme.onSurface;
    return Padding(
      padding: const EdgeInsets.only(right: 8),
      child: InkWell(
        borderRadius: BorderRadius.circular(40),
        onTap: onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 180),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          decoration: BoxDecoration(
            color: selected && style.glass ? null : fill,
            gradient: selected && style.glass ? LinearGradient(colors: [scheme.primary, scheme.secondary]) : null,
            borderRadius: BorderRadius.circular(40),
            border: Border.all(
              color: heavy ? style.border : (selected ? Colors.transparent : style.border.withValues(alpha: 0.6)),
              width: heavy ? 2 : 1,
            ),
            boxShadow: heavy && selected ? [BoxShadow(color: style.border, offset: const Offset(2, 2))] : null,
          ),
          child:
              Text(label, style: TextStyle(color: textColor, fontWeight: selected ? FontWeight.w700 : FontWeight.w500)),
        ),
      ),
    );
  }
}

class TaskFilterBar extends ConsumerWidget {
  const TaskFilterBar({super.key});

  static const options = [
    (null, 'Heute'),
    (TaskView.mine, 'Meine'),
    (TaskView.forMe, 'Für mich'),
    (TaskView.family, 'Familie')
  ];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final current = ref.watch(todayTaskFilterProvider);
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
      child: Row(
        children: [
          for (final (view, label) in options)
            StylePill(
              key: Key('today-filter-${view?.apiName ?? 'today'}'),
              label: label,
              selected: current == view,
              onTap: () => ref.read(todayTaskFilterProvider.notifier).state = view,
            ),
        ],
      ),
    );
  }
}

/// Aufgaben zum direkten Abhaken; zeigt, wem eine Aufgabe gehört.
class TaskChecklist extends ConsumerStatefulWidget {
  final List<Task> tasks;
  final bool online;
  const TaskChecklist({super.key, required this.tasks, required this.online});

  @override
  ConsumerState<TaskChecklist> createState() => _TaskChecklistState();
}

class _TaskChecklistState extends ConsumerState<TaskChecklist> {
  final _done = <String>{};

  Future<void> _complete(Task t) async {
    setState(() => _done.add(t.identity));
    try {
      final sent = await ref.read(apiClientProvider).completeTask(t.uid, provider: t.provider, account: t.account, title: t.title);
      if (!sent && mounted) showInfo(context, 'Ohne Netz gemerkt – wird gesendet, sobald der Hub erreichbar ist');
      if (sent) await refreshTasks(ref);
    } catch (e) {
      if (!mounted) return;
      setState(() => _done.remove(t.identity));
      showError(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final me = ref.watch(sessionProvider).user?.id;
    final people = {for (final p in ref.watch(peopleProvider).valueOrNull ?? const <Person>[]) p.id: p};
    return Column(
      children: [
        for (final t in widget.tasks.take(6))
          Padding(
            key: ValueKey(t.identity),
            padding: const EdgeInsets.symmetric(vertical: 1),
            child: Row(
              children: [
                if (t.isHabitica)
                  HabiticaTaskButtons(task: t, enabled: widget.online, onChanged: () => refreshTasks(ref))
                else
                  Checkbox(
                    shape: const CircleBorder(),
                    value: _done.contains(t.identity) || t.done,
                    visualDensity: VisualDensity.compact,
                    // Nextcloud-Aufgaben gehen auch offline (werden gemerkt), Habitica nicht
                    onChanged: _done.contains(t.identity) || t.localOnly ? null : (_) => _complete(t),
                  ),
                Expanded(
                  child: Text(
                    t.title,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: _done.contains(t.identity)
                        ? TextStyle(
                            decoration: TextDecoration.lineThrough,
                            color: theme.colorScheme.onSurfaceVariant,
                          )
                        : null,
                  ),
                ),
                _TaskTag(task: t, me: me, people: people),
              ],
            ),
          ),
      ],
    );
  }
}

class _TaskTag extends StatelessWidget {
  final Task task;
  final int? me;
  final Map<int, Person> people;
  const _TaskTag({required this.task, required this.me, required this.people});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final who = task.assignee != null && task.assignee != me ? people[task.assignee] : null;
    if (who != null) return PersonAvatar.of(who, size: 24);
    final overdue = task.isOverdue(DateTime.now());
    final due = taskDueLabel(task);
    final label = due.isNotEmpty ? due : (task.listKind == 'family' ? 'Familie' : null);
    if (label == null) return const SizedBox.shrink();
    final color = overdue ? scheme.error : scheme.primary; // primary: auf jedem Kartenhintergrund lesbar
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.16),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(label, style: TextStyle(fontSize: 11, color: color, fontWeight: FontWeight.w600)),
    );
  }
}

/// Die ersten offenen Artikel zum Abhaken plus Eingabe „Hinzufügen…“.
class ShoppingQuick extends ConsumerStatefulWidget {
  final int openCount;
  final bool online;
  const ShoppingQuick({super.key, required this.openCount, required this.online});

  @override
  ConsumerState<ShoppingQuick> createState() => _ShoppingQuickState();
}

class _ShoppingQuickState extends ConsumerState<ShoppingQuick> {
  final _add = TextEditingController();
  final _done = <String>{};

  @override
  void dispose() {
    _add.dispose();
    super.dispose();
  }

  Future<void> _refresh() async {
    await Future.wait([
      ref.read(shoppingProvider.notifier).refresh(),
      ref.read(todayProvider.notifier).refresh(),
    ]);
  }

  Future<void> _check(ShoppingItem item) async {
    setState(() => _done.add(item.uid));
    var sent = true;
    if (await runChange(context, () async => sent = await ref.read(apiClientProvider).setShoppingDone(item.uid, true, name: item.summary))) {
      if (sent) await _refresh().catchError((_) => <Object?>[]);
    } else if (mounted) {
      setState(() => _done.remove(item.uid));
    }
  }

  Future<void> _submit(String value) async {
    final item = value.trim();
    if (item.isEmpty) return;
    var sent = true;
    if (await runChange(context, () async => sent = await ref.read(apiClientProvider).addShoppingItem(item))) {
      _add.clear();
      if (sent) await _refresh().catchError((_) => <Object?>[]);
    }
  }

  @override
  Widget build(BuildContext context) {
    final muted = TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant);
    final data = ref.watch(shoppingProvider).valueOrNull?.data;
    final open = [for (final g in data?.groups ?? const []) ...g.items.where((i) => !i.done)];
    final count = widget.openCount;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
            count == 0
                ? 'Einkaufsliste ist leer'
                : count == 1
                    ? '1 Artikel offen'
                    : '$count Artikel offen',
            style: muted),
        for (final i in open.take(4))
          Row(
            key: ValueKey('shop-${i.uid}'),
            children: [
              Checkbox(
                value: _done.contains(i.uid),
                visualDensity: VisualDensity.compact,
                onChanged: _done.contains(i.uid) || i.localOnly ? null : (_) => _check(i),
              ),
              Expanded(child: Text(i.summary, maxLines: 1, overflow: TextOverflow.ellipsis)),
              if (i.pending) const Icon(Icons.cloud_upload_outlined, size: 16),
            ],
          ),
        if (open.length > 4)
          Padding(padding: const EdgeInsets.only(left: 12), child: Text('+ ${open.length - 4} weitere', style: muted)),
        Padding( // auch offline: wird gemerkt
            padding: const EdgeInsets.only(top: 6),
            child: TextField(
              key: const Key('today-shopping-add'),
              controller: _add,
              textInputAction: TextInputAction.done,
              textCapitalization: TextCapitalization.sentences,
              onSubmitted: _submit,
              decoration: InputDecoration(
                isDense: true,
                hintText: 'Hinzufügen…',
                prefixIcon: const Icon(Icons.add, size: 20),
                filled: true,
                fillColor: Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.05),
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: BorderSide.none),
              ),
            ),
          ),
      ],
    );
  }
}

/// Wochenleiste Mo–So mit Bild oder Symbol, heute hervorgehoben.
class MealWeekStrip extends ConsumerWidget {
  final VoidCallback? onTap;
  const MealWeekStrip({super.key, this.onTap});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final now = DateTime.now();
    final week = ref.watch(mealsProvider(isoWeekOf(now))).valueOrNull?.data;
    if (week == null || week.days.isEmpty) return const SizedBox.shrink();
    final theme = Theme.of(context);
    final style = HubStyle.of(context);
    final days = week.days.take(7).toList();
    return LayoutBuilder(builder: (context, box) {
      // alle sieben Tage ohne Scrollen, Kacheln passen sich der Breite an
      const gap = 6.0;
      final slot = ((box.maxWidth - gap * (days.length - 1)) / days.length).clamp(36.0, 56.0);
      final tile = slot - 4;
      return SizedBox(
        height: tile + 40,
        child: ListView.separated(
          key: const Key('today-meal-week'),
          scrollDirection: Axis.horizontal,
          itemCount: days.length,
          separatorBuilder: (_, __) => const SizedBox(width: gap),
          itemBuilder: (context, i) {
            final d = days[i];
            final isToday = d.date.year == now.year && d.date.month == now.month && d.date.day == now.day;
            final entry = d.entries.isEmpty ? null : d.entries.first;
            final tileRadius = BorderRadius.circular(style.radius >= 20 ? 14 : style.radius / 1.5);
            return InkWell(
              onTap: onTap,
              borderRadius: tileRadius,
              child: SizedBox(
                width: slot,
                child: Column(
                  children: [
                    Text(DateFormat('E', 'de_DE').format(d.date).substring(0, 2),
                        style: theme.textTheme.labelMedium?.copyWith(
                            fontWeight: isToday ? FontWeight.w800 : FontWeight.w500,
                            color: isToday ? theme.colorScheme.primary : null)),
                    const SizedBox(height: 4),
                    Container(
                      width: tile,
                      height: tile,
                      clipBehavior: Clip.antiAlias,
                      decoration: BoxDecoration(
                        color: entry == null
                            ? theme.colorScheme.onSurface.withValues(alpha: 0.05)
                            : theme.colorScheme.primary.withValues(alpha: 0.14),
                        borderRadius: tileRadius,
                        border: Border.all(
                          color: isToday
                              ? theme.colorScheme.primary
                              : (style.borderWidth >= 2 ? style.border : Colors.transparent),
                          width: isToday ? 2 : (style.borderWidth >= 2 ? 2 : 0),
                        ),
                      ),
                      child: entry?.image != null
                          ? Image.network(entry!.image!,
                              fit: BoxFit.cover, errorBuilder: (_, __, ___) => const Icon(Icons.restaurant, size: 20))
                          : Icon(entry == null ? Icons.remove : Icons.restaurant,
                              size: 20, color: theme.colorScheme.onSurfaceVariant),
                    ),
                    const SizedBox(height: 2),
                    Text(entry?.title ?? '',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
                  ],
                ),
              ),
            );
          },
        ),
      );
    });
  }
}

/// Kleine Kachel „Heute · 2 Termine“ für das Kachel-Layout.
class EventsTile extends StatelessWidget {
  final int count;
  final String? next;
  const EventsTile({super.key, required this.count, this.next});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(Icons.calendar_month, color: theme.colorScheme.primary),
            const SizedBox(width: 8),
            Text('$count', style: theme.textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w800)),
          ],
        ),
        Text(count == 1 ? 'Termin' : 'Termine', style: theme.textTheme.bodyMedium),
        if (next != null)
          Text(next!,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
      ],
    );
  }
}
