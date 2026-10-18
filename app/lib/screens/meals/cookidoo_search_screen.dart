import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/common.dart';
import '../../models/meals.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';
import '../../l10n/l10n.dart';

/// Search a recipe in a source (Cookidoo, Mealie …) and plan it on [day]. Closes with `true` when planned.
class CookidooSearchScreen extends ConsumerStatefulWidget {
  final DateTime day;
  final String source;
  final String sourceName;
  const CookidooSearchScreen({super.key, required this.day, this.source = 'cookidoo', this.sourceName = 'Cookidoo'});

  @override
  ConsumerState<CookidooSearchScreen> createState() => _CookidooSearchScreenState();
}

class _CookidooSearchScreenState extends ConsumerState<CookidooSearchScreen> {
  final _query = TextEditingController();
  Timer? _debounce;
  SourceResult<CookidooRecipe>? _result;
  bool _loading = false;
  String? _planning; // Rezept-ID, die gerade eingeplant wird

  @override
  void dispose() {
    _debounce?.cancel();
    _query.dispose();
    super.dispose();
  }

  void _onQuery(String _) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 800), _search);
  }

  Future<void> _search() async {
    final q = _query.text.trim();
    if (q.length < 3) {
      setState(() => _result = null);
      return;
    }
    setState(() => _loading = true);
    try {
      final api = ref.read(apiClientProvider);
      final r = widget.source == 'cookidoo' ? await api.searchCookidoo(q) : await api.searchRecipeSource(widget.source, q);
      if (mounted && _query.text.trim() == q) setState(() => _result = r);
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _plan(CookidooRecipe recipe) async {
    setState(() => _planning = recipe.id);
    final api = ref.read(apiClientProvider);
    final ok = await runAction(context, () => widget.source == 'cookidoo'
        ? api.planCookidoo(widget.day, recipe.id)
        : api.planFromSource(widget.source, widget.day, recipe.id));
    if (!mounted) return;
    setState(() => _planning = null);
    if (ok) Navigator.pop(context, true);
  }

  @override
  Widget build(BuildContext context) {
    final result = _result;
    return Scaffold(
      appBar: AppBar(title: Text(l10n.recipeFor(localDate('EEEE').format(widget.day)))),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
            child: TextField(
              controller: _query,
              autofocus: true,
              textInputAction: TextInputAction.search,
              decoration: InputDecoration(
                prefixIcon: Icon(Icons.search),
                hintText: widget.source == 'cookidoo' ? l10n.searchCookidoo : l10n.searchInSource(widget.sourceName),
              ),
              onChanged: _onQuery,
              onSubmitted: (_) => _search(),
            ),
          ),
          if (_loading) const LinearProgressIndicator(),
          Expanded(
            child: result == null
                ? EmptyHint(icon: Icons.restaurant_menu, text: l10n.min3Letters)
                : ListView(
                    children: [
                      SourceBanner(source: widget.sourceName, status: result.status, error: result.error),
                      if (result.status == SourceStatus.ok && result.items.isEmpty)
                        EmptyHint(icon: Icons.search_off, text: l10n.nothingFound),
                      for (final r in result.items)
                        ListTile(
                          leading: RecipeThumb(url: r.thumbnail),
                          title: Text(r.name),
                          trailing: _planning == r.id
                              ? const HubLoader.small()
                              : const Icon(Icons.add_circle_outline),
                          onTap: _planning == null ? () => _plan(r) : null,
                        ),
                    ],
                  ),
          ),
        ],
      ),
    );
  }
}

/// Kleines Rezeptbild mit Platzhalter (auch ohne Netz).
class RecipeThumb extends StatelessWidget {
  final String? url;
  final double size;
  const RecipeThumb({super.key, this.url, this.size = 48});

  @override
  Widget build(BuildContext context) {
    final fallback = Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surfaceContainerHigh,
        borderRadius: BorderRadius.circular(8),
      ),
      child: const Icon(Icons.restaurant, size: 20),
    );
    if (url == null || url!.isEmpty) return fallback;
    return ClipRRect(
      borderRadius: BorderRadius.circular(8),
      child: Image.network(url!, width: size, height: size, fit: BoxFit.cover, errorBuilder: (_, __, ___) => fallback),
    );
  }
}
