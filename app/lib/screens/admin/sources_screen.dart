import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../l10n/l10n.dart';
import '../../models/admin.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';

final adminSourcesProvider = FutureProvider.autoDispose<List<SourceArea>>((ref) => ref.watch(apiClientProvider).adminSources());

/// Administration → Sources per area: where tasks, shopping and events come from.
class SourcesScreen extends StatelessWidget {
  const SourcesScreen({super.key});

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: Text(l10n.sourcesAdmin)),
        body: const SingleChildScrollView(padding: EdgeInsets.only(bottom: 24), child: SourcesEditor()),
      );
}

/// Also used in the setup wizard (services step).
class SourcesEditor extends ConsumerWidget {
  const SourcesEditor({super.key});

  static String _title(String area) => switch (area) {
        'tasks' => l10n.areaTasksMulti,
        'shopping' => l10n.areaShoppingSingle,
        'calendar' => l10n.areaCalendarMulti,
        _ => area,
      };

  Future<void> _save(BuildContext context, WidgetRef ref, SourceArea area, List<String> selected) async {
    if (await runAction(context, () => ref.read(apiClientProvider).setSources(area.area, selected))) {
      ref.invalidate(adminSourcesProvider);
      ref.invalidate(modulesProvider);
      ref.invalidate(taskAccountsProvider);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(adminSourcesProvider);
    final muted = TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant);
    return async.when(
      loading: () => const Padding(padding: EdgeInsets.all(24), child: Center(child: HubLoader())),
      // Compact: the editor also sits inside the wizard's list, where a full-size error view has no height
      error: (e, _) => ListTile(
        leading: const Icon(Icons.cloud_off),
        title: Text(errorText(e)),
        trailing: TextButton(onPressed: () => ref.invalidate(adminSourcesProvider), child: Text(l10n.retry)),
      ),
      data: (areas) => Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
          child: Text(l10n.sourcesTitle, style: Theme.of(context).textTheme.titleMedium),
        ),
        Padding(padding: const EdgeInsets.fromLTRB(16, 0, 16, 8), child: Text(l10n.sourcesHint, style: muted)),
        for (final area in areas) ...[
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
            child: Text(_title(area.area), style: Theme.of(context).textTheme.titleSmall),
          ),
          for (final s in area.sources)
            _option(context, ref, area, s, muted),
          if (area.recipeIngredients != null) _recipeIngredients(context, ref, area.recipeIngredients!, muted),
        ],
      ]),
    );
  }

  Widget _recipeIngredients(BuildContext context, WidgetRef ref, String mode, TextStyle muted) {
    Future<void> save(String? v) async {
      if (v == null || v == mode) return;
      if (await runAction(context, () => ref.read(apiClientProvider).setRecipeIngredients(v))) {
        ref.invalidate(adminSourcesProvider);
      }
    }

    Widget option(String value, String title, String hint) => RadioListTile<String>(
          key: Key('recipe-ingredients-$value'),
          value: value,
          title: Text(title),
          subtitle: Text(hint, style: muted),
        );
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
        child: Text(l10n.recipeIngredientsTitle, style: Theme.of(context).textTheme.titleSmall),
      ),
      RadioGroup<String>(
        groupValue: mode,
        onChanged: save,
        child: Column(children: [
          option('merge', l10n.recipeIngredientsMerge, l10n.recipeIngredientsMergeHint),
          option('source', l10n.recipeIngredientsSource, l10n.recipeIngredientsSourceHint),
        ]),
      ),
    ]);
  }

  Widget _option(BuildContext context, WidgetRef ref, SourceArea area, SourceOption s, TextStyle muted) {
    final usable = s.configured && s.active;
    final subtitle = Text(usable ? s.description : l10n.sourceNotSetUp, maxLines: 2, overflow: TextOverflow.ellipsis, style: muted);
    final selected = [for (final o in area.sources) if (o.selected) o.id];
    if (area.multiple) {
      return CheckboxListTile(
        key: Key('source-${area.area}-${s.id}'),
        value: s.selected,
        title: Text(s.name),
        subtitle: subtitle,
        onChanged: !usable ? null : (v) {
          final next = v == true ? [...selected, s.id] : selected.where((id) => id != s.id).toList();
          if (next.isEmpty) {
            showInfo(context, l10n.sourceKeepOne);
            return;
          }
          _save(context, ref, area, next);
        },
      );
    }
    return RadioGroup<String>(
      groupValue: selected.isEmpty ? null : selected.first,
      onChanged: (v) => v == null ? null : _save(context, ref, area, [v]),
      child: RadioListTile<String>(
        key: Key('source-${area.area}-${s.id}'),
        value: s.id,
        enabled: usable,
        title: Text(s.name),
        subtitle: subtitle,
      ),
    );
  }
}
