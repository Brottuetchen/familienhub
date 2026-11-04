import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/themes.dart';
import '../../providers/providers.dart';
import '../../providers/theme_provider.dart';
import '../../widgets/common.dart';
import '../../l10n/l10n.dart';

/// Admin only: install themes from GitHub and remove installed ones. Choosing a theme is personal (AppearanceScreen).
class AdminThemesScreen extends ConsumerWidget {
  const AdminThemesScreen({super.key});

  Future<void> _install(BuildContext context, WidgetRef ref) async {
    final url = await showDialog<String>(
      context: context,
      builder: (ctx) {
        final c = TextEditingController();
        return AlertDialog(
          title: Text(l10n.themeFromGithub),
          content: TextField(
            controller: c,
            autofocus: true,
            keyboardType: TextInputType.url,
            decoration: InputDecoration(
              labelText: l10n.githubAddress,
              hintText: 'https://github.com/name/repo',
              helperText: l10n.themeRepoNeedsJson,
            ),
            onSubmitted: (v) => Navigator.pop(ctx, v),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: Text(l10n.cancel)),
            FilledButton(onPressed: () => Navigator.pop(ctx, c.text), child: Text(l10n.install)),
          ],
        );
      },
    );
    if (url == null || url.trim().isEmpty || !context.mounted) return;
    if (await runAction(context, () => ref.read(apiClientProvider).installTheme(url.trim()))) {
      ref.invalidate(themesProvider);
    }
  }

  Future<void> _delete(BuildContext context, WidgetRef ref, ThemeSpec spec) async {
    final sure = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(l10n.themeRemoveQuestion),
        content: Text(l10n.themeRemoveHint(spec.name)),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: Text(l10n.cancel)),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: Text(l10n.remove)),
        ],
      ),
    );
    if (sure != true || !context.mounted) return;
    if (await runAction(context, () => ref.read(apiClientProvider).deleteTheme(spec.id))) {
      if (ref.read(themeChoiceProvider)?.id == spec.id) await ref.read(themeChoiceProvider.notifier).select(null);
      ref.invalidate(themesProvider);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(themesProvider);
    return Scaffold(
      appBar: AppBar(title: Text(l10n.themes)),
      floatingActionButton: FloatingActionButton.extended(
        key: const Key('theme-install'),
        onPressed: () => _install(context, ref),
        icon: const Icon(Icons.download_outlined),
        label: Text(l10n.fromGithub),
      ),
      body: HubRefresh(
        onRefresh: () => ref.refresh(themesProvider.future),
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.only(bottom: 96),
          children: [
            ...async.when(
              loading: () => const [Padding(padding: EdgeInsets.all(24), child: Center(child: HubLoader()))],
              error: (e, _) => [ErrorView(error: e, onRetry: () => ref.invalidate(themesProvider))],
              data: (themes) => [
                for (final t in themes.where((t) => t.usable))
                  ListTile(
                    key: Key('admin-theme-${t.id}'),
                    leading: const Icon(Icons.palette_outlined),
                    title: Text(t.name),
                    subtitle: Text(t.builtin ? l10n.themeBuiltin : l10n.themeInstalled),
                    trailing: t.builtin
                        ? null
                        : IconButton(
                            tooltip: l10n.themeRemove,
                            onPressed: () => _delete(context, ref, t),
                            icon: const Icon(Icons.delete_outline),
                          ),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
