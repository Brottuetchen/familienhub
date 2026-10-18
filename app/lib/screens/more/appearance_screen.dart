import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/themes.dart';
import '../../providers/providers.dart';
import '../../providers/theme_provider.dart';
import '../../widgets/common.dart';
import '../../l10n/l10n.dart';

/// Farbschema wählen (pro Gerät). Admins können Themes aus GitHub installieren und wieder entfernen.
class AppearanceScreen extends ConsumerWidget {
  const AppearanceScreen({super.key});

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
    final chosen = ref.watch(themeChoiceProvider);
    final isAdmin = ref.watch(sessionProvider).user?.isAdmin ?? false;
    final choice = ref.read(themeChoiceProvider.notifier);

    return Scaffold(
      appBar: AppBar(title: Text(l10n.appearance)),
      floatingActionButton: isAdmin
          ? FloatingActionButton.extended(
              onPressed: () => _install(context, ref),
              icon: const Icon(Icons.download_outlined),
              label: Text(l10n.fromGithub),
            )
          : null,
      body: HubRefresh(
        onRefresh: () => ref.refresh(themesProvider.future),
        child: ListView(
          padding: const EdgeInsets.only(bottom: 96),
          children: [
            Padding(
              padding: EdgeInsets.fromLTRB(16, 8, 16, 8),
              child: Text(l10n.onlyThisDevice),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
              child: SegmentedButton<ThemeMode>(
                key: const Key('theme-mode'),
                segments: [
                  ButtonSegment(value: ThemeMode.system, label: Text(l10n.modeAuto), icon: Icon(Icons.brightness_auto_outlined)),
                  ButtonSegment(value: ThemeMode.light, label: Text(l10n.modeLight), icon: Icon(Icons.light_mode_outlined)),
                  ButtonSegment(value: ThemeMode.dark, label: Text(l10n.modeDark), icon: Icon(Icons.dark_mode_outlined)),
                ],
                selected: {ref.watch(themeModeProvider)},
                onSelectionChanged: (s) => ref.read(themeModeProvider.notifier).select(s.first),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
              child: SegmentedButton<String>(
                key: const Key('app-language'),
                segments: [
                  ButtonSegment(value: 'system', label: Text(l10n.languageSystem), icon: const Icon(Icons.translate)),
                  for (final e in appLanguages.entries) ButtonSegment(value: e.key, label: Text(e.value)),
                ],
                selected: {ref.watch(languageChoiceProvider)},
                onSelectionChanged: (s) => ref.read(languageChoiceProvider.notifier).select(s.first),
              ),
            ),
            _ThemeTile(
              key: const Key('theme-standard'),
              name: l10n.themeDefault,
              subtitle: l10n.themeDefaultHint,
              swatches: const [Color(0xFF0B0C16), Color(0xFF151726), Color(0xFFA78BFA), Color(0xFF00B4D8)],
              selected: chosen == null,
              onTap: () => choice.select(null),
            ),
            ...async.when(
              loading: () => const [Padding(padding: EdgeInsets.all(24), child: Center(child: HubLoader()))],
              error: (e, _) => [ErrorView(error: e, onRetry: () => ref.invalidate(themesProvider))],
              data: (themes) => [
                for (final t in themes.where((t) => t.usable))
                  _ThemeTile(
                    key: Key('theme-${t.id}'),
                    name: t.name,
                    subtitle: [
                      t.builtin ? l10n.themeBuiltin : l10n.themeInstalled,
                      if (t.hasBothModes) l10n.themeLightDark else (t.brightness == Brightness.dark ? l10n.themeDarkOnly : l10n.themeLightOnly),
                    ].join(' · '),
                    // Vorschau in der Fassung, die gerade gilt
                    swatches: [
                      for (final k in ['background', 'surface', 'primary', 'secondary'])
                        t.forBrightness(Theme.of(context).brightness).color(k)!,
                    ],
                    selected: chosen?.id == t.id,
                    onTap: () => choice.select(t),
                    onDelete: isAdmin && !t.builtin ? () => _delete(context, ref, t) : null,
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _ThemeTile extends StatelessWidget {
  final String name;
  final String subtitle;
  final List<Color> swatches;
  final bool selected;
  final VoidCallback onTap;
  final VoidCallback? onDelete;

  const _ThemeTile({
    super.key,
    required this.name,
    required this.subtitle,
    required this.swatches,
    required this.selected,
    required this.onTap,
    this.onDelete,
  });

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return ListTile(
      onTap: onTap,
      leading: SizedBox(
        width: 64,
        child: Row(
          children: [
            for (final c in swatches)
              Container(
                width: 16,
                height: 32,
                decoration: BoxDecoration(color: c, border: Border.all(color: scheme.outlineVariant, width: 0.5)),
              ),
          ],
        ),
      ),
      title: Text(name),
      subtitle: Text(subtitle),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (onDelete != null)
            IconButton(tooltip: l10n.themeRemove, onPressed: onDelete, icon: const Icon(Icons.delete_outline)),
          Icon(selected ? Icons.check_circle : Icons.circle_outlined,
              color: selected ? scheme.primary : scheme.onSurfaceVariant),
        ],
      ),
    );
  }
}
