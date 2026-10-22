import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/account.dart';
import '../../models/common.dart';
import '../../models/task.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';
import 'habitica_tasks.dart';
import '../main_shell.dart';
import '../more/caldav_account_screen.dart';
import '../../l10n/l10n.dart';
import '../templates/templates_screen.dart';
import '../lists/named_lists_screen.dart';

part 'task_list.dart';
part 'task_details.dart';
part 'task_create_sheet.dart';
part 'task_edit_sheet.dart';

/// „überfällig“, „heute“, „morgen“, „Fr, 17.10.“ oder leer.
String taskDueLabel(Task t, {DateTime? now}) {
  if (t.due == null) return '';
  final n = now ?? DateTime.now();
  if (t.isOverdue(n)) return l10n.overdue;
  final label = dayLabel(t.due!, now: n);
  if (label == l10n.today || label == l10n.tomorrow) {
    final time = t.dueIsDate ? '' : ' ${timeLabel(t.due!)}';
    return '${label.toLowerCase()}$time';
  }
  return localDate('E, d.M.').format(t.due!);
}


class TasksScreen extends ConsumerStatefulWidget {
  const TasksScreen({super.key});

  @override
  ConsumerState<TasksScreen> createState() => _TasksScreenState();
}


class _TasksScreenState extends ConsumerState<TasksScreen> with SingleTickerProviderStateMixin {
  late final TabController _tabs;
  Task? _selected;
  TaskView _selectedView = TaskView.mine;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(
      length: TaskView.values.length,
      vsync: this,
      initialIndex: TaskView.values.indexOf(ref.read(taskViewProvider)),
    );
    _tabs.addListener(() {
      if (!_tabs.indexIsChanging) {
        ref.read(taskViewProvider.notifier).state = TaskView.values[_tabs.index];
      }
    });
  }

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  /// No provider choice: the hub puts the task where the recipient works (own tasks: my preferred place,
  /// family tasks: the family list). Native Habitica types are created in the Habitica account screen.
  Future<void> _create() async {
    final view = ref.read(taskViewProvider);
    await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (_) => ProtectedReadModal(
        provider: tasksProvider(view),
        child: const TaskCreateSheet(),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    // Push-Ziel „/tasks?view=for_me“ schaltet den Reiter um
    ref.listen<TaskView>(taskViewProvider, (_, view) {
      final i = TaskView.values.indexOf(view);
      if (_tabs.index != i) _tabs.animateTo(i);
    });
    final wide = isWide(context);
    if (_selected != null) {
      ref.listen(tasksProvider(_selectedView), (_, next) {
        if (next.valueOrNull == null) setState(() => _selected = null);
      });
    }

    final lists = TabBarView(
      controller: _tabs,
      children: [
        for (final v in TaskView.values)
          _TaskList(
            view: v,
            selectedUid: wide ? _selected?.identity : null,
            onOpen: (t) => t.isHabitica ? (ref.read(canEditProvider) ? showNativeEditor(context, ref, t.account, task: t) : null) : wide ? setState(() {
              _selected = t;
              _selectedView = v;
            }) : _showDetails(t, v),
          ),
      ],
    );

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.tabTasks),
        actions: [ReadStatusIcon(result: ref.watch(tasksProvider(ref.watch(taskViewProvider))).valueOrNull),
          IconButton(
            key: const Key('tasks-show-done'),
            tooltip: ref.watch(showDoneTasksProvider) ? l10n.hideDone : l10n.showDone,
            icon: Icon(ref.watch(showDoneTasksProvider) ? Icons.visibility_off_outlined : Icons.visibility_outlined),
            onPressed: () => ref.read(showDoneTasksProvider.notifier).state = !ref.read(showDoneTasksProvider),
          ),
          if (ref.watch(canActProvider) && ref.watch(taskAccountsProvider).valueOrNull?.any((p) => p.id == 'habitica') == true)
          IconButton(tooltip: l10n.habiticaAccountSelection, icon: const Icon(Icons.account_tree_outlined), onPressed: () async {
            await Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => ProtectedReadModal(
              provider: tasksProvider(TaskView.mine), child: const HabiticaAccountScreen())));
            ref.invalidate(taskAccountsProvider); await refreshTasks(ref);
          }),
          PopupMenuButton<String>(
            key: const Key('tasks-menu'),
            onSelected: (v) => Navigator.of(context).push(MaterialPageRoute<void>(
                builder: (_) => v == 'lists'
                    ? const NamedListsScreen(kind: 'tasks')
                    : const TemplatesScreen(target: TemplateTarget.tasks))),
            itemBuilder: (_) => [
              PopupMenuItem(value: 'lists', child: Text(l10n.namedLists)),
              PopupMenuItem(value: 'templates', child: Text(l10n.templates)),
            ],
          )],
        bottom: TabBar(
          controller: _tabs,
          isScrollable: !wide,
          tabAlignment: wide ? TabAlignment.fill : TabAlignment.start,
          tabs: [for (final v in TaskView.values) Tab(text: v.label)],
        ),
      ),
      floatingActionButton: ref.watch(canEditProvider)
          ? FloatingActionButton.extended(
              onPressed: _create,
              icon: const Icon(Icons.add),
              label: Text(l10n.task),
            )
          : null,
      body: wide
          ? Row(
              children: [
                Expanded(flex: 5, child: lists),
                const VerticalDivider(width: 1),
                Expanded(
                  flex: 4,
                  child: _selected == null
                      ? EmptyHint(icon: Icons.touch_app_outlined, text: l10n.tapTaskForDetails)
                      : TaskDetails(task: _selected!, view: _selectedView, onClose: () => setState(() => _selected = null)),
                ),
              ],
            )
          : lists,
    );
  }

  void _showDetails(Task t, TaskView view) {
    if (t.isHabitica) {
      if (ref.read(canEditProvider)) showNativeEditor(context, ref, t.account, task: t);
      return;
    }
    showModalBottomSheet<void>(
      context: context,
      useSafeArea: true,
      builder: (ctx) => ProtectedReadModal(
        provider: tasksProvider(view),
        child: TaskDetails(task: t, view: view, onClose: () => Navigator.pop(ctx)),
      ),
    );
  }
}


/// Erledigte Aufgaben einblenden (wie beim Einkauf). Standard: aus.
final showDoneTasksProvider = StateProvider<bool>((_) => false);



/// Star values offered for a task (kids mode); 0 = none.
const _starOptions = [0, 1, 2, 3, 5, 8, 10, 15, 20];
