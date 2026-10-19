import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../l10n/l10n.dart';
import '../../models/meals.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';
import 'recipes_screen.dart';

/// Import a recipe from a link: the hub reads the page, the draft opens in the recipe editor for
/// checking, and only "Save" there stores it. Closes with the saved recipe.
class RecipeImportScreen extends ConsumerStatefulWidget {
  final String? initialUrl;
  const RecipeImportScreen({super.key, this.initialUrl});

  @override
  ConsumerState<RecipeImportScreen> createState() => _RecipeImportScreenState();
}

class _RecipeImportScreenState extends ConsumerState<RecipeImportScreen> {
  late final _link = TextEditingController(text: widget.initialUrl);
  bool _busy = false;
  String? _problem;

  @override
  void initState() {
    super.initState();
    if (widget.initialUrl != null) WidgetsBinding.instance.addPostFrameCallback((_) => _read());
  }

  @override
  void dispose() {
    _link.dispose();
    super.dispose();
  }

  String _message(String status) => switch (status) {
        'no_recipe' => l10n.importNoRecipe,
        'blocked' => l10n.importBlocked,
        'too_large' => l10n.importTooLarge,
        'invalid_url' => l10n.importInvalid,
        _ => l10n.importUnreachable,
      };

  Future<void> _read() async {
    final url = _link.text.trim();
    if (url.isEmpty || _busy) return;
    setState(() {
      _busy = true;
      _problem = null;
    });
    try {
      final result = await ref.read(apiClientProvider).importRecipePreview(url);
      if (!mounted) return;
      final draft = result.recipe;
      if (result.status != 'ok' || draft == null) {
        setState(() {
          _busy = false;
          _problem = _message(result.status);
        });
        return;
      }
      setState(() => _busy = false);
      final saved = await Navigator.push<HubRecipe>(
          context, MaterialPageRoute(builder: (_) => RecipeEditScreen(recipe: draft, hint: l10n.importPreviewHint)));
      if (saved != null && mounted) Navigator.pop(context, saved);
    } catch (e) {
      if (mounted) {
        setState(() => _busy = false);
        showError(context, e);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(l10n.importFromLink)),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        TextField(
          key: const Key('import-link'),
          controller: _link,
          keyboardType: TextInputType.url,
          autocorrect: false,
          textInputAction: TextInputAction.go,
          onSubmitted: (_) => _read(),
          decoration: InputDecoration(labelText: l10n.importLinkLabel, prefixIcon: const Icon(Icons.link)),
        ),
        const SizedBox(height: 12),
        Align(
          alignment: Alignment.centerLeft,
          child: FilledButton.icon(
            key: const Key('import-read'),
            onPressed: _busy ? null : _read,
            icon: _busy
                ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.download),
            label: Text(l10n.importFetch),
          ),
        ),
        if (_problem != null) ...[
          const SizedBox(height: 16),
          Text(_problem!, key: const Key('import-problem'), style: TextStyle(color: theme.colorScheme.error)),
        ],
      ]),
    );
  }
}
