import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../l10n/l10n.dart';
import '../../models/meals.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';
import '../../widgets/hub_image.dart';

/// What the person did in the quick view. `null` = just closed.
enum QuickViewResult { changed, edit }

/// The recipe the quick view is about. [source] is `hub`, `cookidoo`, `mealie` … ([id] is the hub recipe id
/// as text for `hub`). Title, image, time and link are shown at once; the rest is loaded.
class RecipeRef {
  final String source;
  final String id;
  final String title;
  final String? image;
  final String? url;
  final int? minutes;

  /// Display name of a plugin source (the server sends it); the built-in sources are named in the app.
  final String? sourceLabel;
  const RecipeRef(
      {required this.source, required this.id, required this.title, this.image, this.url, this.minutes, this.sourceLabel});

  String get sourceName => source == 'hub' ? l10n.recipeBook : recipeSourceNames[source] ?? sourceLabel ?? source;
}

/// One bottom sheet for every recipe: from search results (hub, Cookidoo, Mealie …) and from the week plan.
///
/// - [planDay]: the day the recipe is being picked for (search flow); the main action plans it there.
/// - [onRemove]: opened from the plan; offers "remove from plan".
/// - [onEdit]: hub recipes of the recipe book can be edited (returns [QuickViewResult.edit]).
Future<QuickViewResult?> showRecipeQuickView(BuildContext context, RecipeRef recipe,
    {DateTime? planDay, Future<void> Function()? onRemove, bool canEdit = false}) {
  return showModalBottomSheet<QuickViewResult>(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    showDragHandle: true,
    builder: (_) => RecipeQuickView(recipe: recipe, planDay: planDay, onRemove: onRemove, canEditRecipe: canEdit),
  );
}

class RecipeQuickView extends ConsumerStatefulWidget {
  final RecipeRef recipe;
  final DateTime? planDay;
  final Future<void> Function()? onRemove;
  final bool canEditRecipe;
  const RecipeQuickView({super.key, required this.recipe, this.planDay, this.onRemove, this.canEditRecipe = false});

  @override
  ConsumerState<RecipeQuickView> createState() => _RecipeQuickViewState();
}

class _RecipeQuickViewState extends ConsumerState<RecipeQuickView> {
  late Future<RecipeDetails> _future = _load();
  bool _busy = false;

  RecipeRef get r => widget.recipe;
  bool get _hub => r.source == 'hub';

  Future<RecipeDetails> _load() => ref.read(apiClientProvider).recipeDetails(r.source, r.id);

  Future<void> _run(Future<void> Function() action, {bool closeOnSuccess = false, String? message}) async {
    setState(() => _busy = true);
    final ok = await runAction(context, action);
    if (!mounted) return;
    setState(() => _busy = false);
    if (!ok) return;
    if (message != null) showInfo(context, message);
    if (closeOnSuccess) Navigator.pop(context, QuickViewResult.changed);
  }

  Future<void> _plan() async {
    final api = ref.read(apiClientProvider);
    var day = widget.planDay;
    if (day == null) {
      final now = DateTime.now();
      day = await showDatePicker(
          context: context, initialDate: now, firstDate: now.subtract(const Duration(days: 7)), lastDate: now.add(const Duration(days: 365)));
      if (day == null || !mounted) return;
    }
    final chosen = day;
    await _run(
      () => _hub
          ? api.planRecipe(chosen, int.parse(r.id))
          : r.source == 'cookidoo' ? api.planCookidoo(chosen, r.id) : api.planFromSource(r.source, chosen, r.id),
      closeOnSuccess: widget.planDay != null,
      message: widget.planDay == null ? l10n.plannedOn(dayLabel(chosen)) : null,
    );
  }

  Future<void> _shopping() async {
    final api = ref.read(apiClientProvider);
    setState(() => _busy = true);
    try {
      final String message;
      if (_hub) {
        message = l10n.ingredientsToListCount(await api.recipeToShopping(int.parse(r.id)));
      } else if (r.source == 'cookidoo') {
        message = l10n.ingredientsOnCookidooList(await api.cookidooToShopping([r.id]));
      } else {
        await api.sourceToShopping(r.source, [r.id]);
        message = l10n.ingredientsToList;
      }
      if (mounted) showInfo(context, message);
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  /// Icon + label that wraps instead of overflowing at large text sizes.
  Widget _label(IconData icon, String text) => Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(icon, size: 18),
        const SizedBox(width: 8),
        Flexible(child: Text(text, textAlign: TextAlign.center)),
      ]);

  Future<void> _openLink(String url) => launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final canEdit = ref.watch(canEditProvider);
    return FutureBuilder<RecipeDetails>(
      future: _future,
      builder: (context, snap) {
        final loading = snap.connectionState != ConnectionState.done;
        final details = snap.data;
        final failed = !loading && (snap.hasError || (details != null && !details.isOk));
        final ok = details != null && details.isOk ? details : null;
        final title = (ok?.title.isNotEmpty ?? false) ? ok!.title : r.title;
        final image = ok?.image ?? r.image;
        final minutes = ok?.minutes ?? r.minutes;
        final servings = ok?.servings;
        final url = ok?.url ?? r.url;
        final muted = theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant);

        return SingleChildScrollView(
          key: const Key('recipe-quick-view'),
          padding: EdgeInsets.fromLTRB(20, 0, 20, 24 + MediaQuery.viewInsetsOf(context).bottom),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (image != null && image.isNotEmpty)
                ClipRRect(
                  borderRadius: BorderRadius.circular(12),
                  child: SizedBox(
                    height: 170,
                    child: HubImage(url: image, placeholder: const SizedBox.shrink()),
                  ),
                ),
              if (image != null && image.isNotEmpty) const SizedBox(height: 12),
              Text(title, key: const Key('recipe-quick-title'), style: theme.textTheme.titleLarge),
              const SizedBox(height: 8),
              Wrap(spacing: 16, runSpacing: 4, crossAxisAlignment: WrapCrossAlignment.center, children: [
                if (minutes != null)
                  Row(mainAxisSize: MainAxisSize.min, children: [
                    const Icon(Icons.schedule, size: 18),
                    const SizedBox(width: 4),
                    Flexible(child: Text(l10n.minutesShort(minutes))),
                  ]),
                if (servings != null)
                  Row(mainAxisSize: MainAxisSize.min, children: [
                    const Icon(Icons.people_outline, size: 18),
                    const SizedBox(width: 4),
                    Flexible(child: Text(l10n.servingsOnly(servings))),
                  ]),
                Text(r.sourceName, style: muted),
              ]),
              const SizedBox(height: 16),
              if (canEdit) ...[
                // One full-width button per row: long labels wrap instead of running off the sheet at large text
                FilledButton(
                  key: const Key('recipe-plan'),
                  onPressed: _busy ? null : _plan,
                  child: _label(Icons.event, widget.planDay == null ? l10n.planOnDay : l10n.planOnDate(dayLabel(widget.planDay!))),
                ),
                const SizedBox(height: 8),
                FilledButton.tonal(
                  key: const Key('recipe-shopping'),
                  onPressed: _busy ? null : _shopping,
                  child: _label(Icons.add_shopping_cart, l10n.ingredientsToList),
                ),
                if (widget.onRemove != null) ...[
                  const SizedBox(height: 8),
                  OutlinedButton(
                    key: const Key('recipe-remove'),
                    onPressed: _busy ? null : () => _run(widget.onRemove!, closeOnSuccess: true),
                    child: _label(Icons.event_busy, l10n.removeFromPlan),
                  ),
                ],
                const SizedBox(height: 8),
              ],
              if (url != null && url.isNotEmpty)
                TextButton(
                  key: const Key('recipe-open-source'),
                  onPressed: () => _openLink(url),
                  child: _label(Icons.open_in_new, _hub ? l10n.openLink : l10n.openInSource(r.sourceName)),
                ),
              if (_hub && canEdit && widget.canEditRecipe)
                TextButton(
                  key: const Key('recipe-quick-edit'),
                  onPressed: () => Navigator.pop(context, QuickViewResult.edit),
                  child: _label(Icons.edit_outlined, l10n.editRecipe),
                ),
              const SizedBox(height: 8),
              if (loading)
                const Padding(padding: EdgeInsets.symmetric(vertical: 24), child: Center(child: HubLoader()))
              else if (failed)
                Column(key: const Key('recipe-quick-error'), crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                  const Icon(Icons.error_outline, size: 36),
                  const SizedBox(height: 8),
                  Text(snap.hasError ? errorText(snap.error!) : (details?.error ?? l10n.recipeDetailsFailed),
                      textAlign: TextAlign.center),
                  const SizedBox(height: 12),
                  Center(
                    child: FilledButton.tonal(
                      key: const Key('recipe-quick-retry'),
                      onPressed: () {
                        setState(() {
                          _future = _load();
                        });
                      },
                      child: Text(l10n.retry),
                    ),
                  ),
                ])
              else if (ok != null) ...[
                if (ok.ingredients.isEmpty && ok.steps.isEmpty) Text(l10n.recipeNoDetails, style: muted),
                if (ok.ingredients.isNotEmpty) ...[
                  Text(l10n.ingredients, style: theme.textTheme.titleMedium),
                  const SizedBox(height: 4),
                  for (final i in ok.ingredients) Padding(padding: const EdgeInsets.symmetric(vertical: 2), child: Text('•  $i')),
                  const SizedBox(height: 16),
                ],
                if (ok.steps.isNotEmpty) ...[
                  Text(l10n.preparation, style: theme.textTheme.titleMedium),
                  const SizedBox(height: 4),
                  for (final (i, step) in ok.steps.indexed)
                    Padding(padding: const EdgeInsets.symmetric(vertical: 4), child: Text('${i + 1}. $step')),
                ],
              ],
            ],
          ),
        );
      },
    );
  }
}
