import 'package:expressive_loading_indicator/expressive_loading_indicator.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../core/theme/hub_style.dart';
import '../models/common.dart';
import '../models/pending.dart';
import '../providers/providers.dart';
import '../services/api_exceptions.dart';
import 'hub_background.dart';

final _time = DateFormat('HH:mm', 'de_DE');

/// Modale Momentaufnahmen dürfen den Zugriff ihres Lesemodells nicht überleben.
class ProtectedReadModal extends ConsumerWidget {
  final ProviderListenable<AsyncValue<Object?>> provider;
  final Widget child;
  const ProtectedReadModal({super.key, required this.provider, required this.child});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (ref.watch(provider).valueOrNull != null) return child;
    final route = ModalRoute.of(context);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (context.mounted && route != null && route.isActive) {
        Navigator.of(context).removeRoute(route);
      }
    });
    return const SizedBox.shrink();
  }
}

/// Ladeanzeige im Material-3-Expressive-Stil: wechselnde Formen statt drehendem Kreis.
class HubLoader extends StatelessWidget {
  final double size;
  final Color? color;
  const HubLoader({super.key, this.size = 48, this.color});

  /// Klein, z. B. in Knöpfen und Listenzeilen.
  const HubLoader.small({super.key, this.color}) : size = 24;

  @override
  Widget build(BuildContext context) => SizedBox.square(
        dimension: size,
        child: ExpressiveLoadingIndicator(
          color: color ?? Theme.of(context).colorScheme.primary,
          constraints: BoxConstraints.tight(Size.square(size)),
          semanticsLabel: 'Lädt',
        ),
      );
}

/// Ziehen zum Aktualisieren – mit der Formen-Ladeanzeige statt des drehenden Kreises.
class HubRefresh extends StatefulWidget {
  final Future<void> Function() onRefresh;
  final Widget child;
  const HubRefresh({super.key, required this.onRefresh, required this.child});

  @override
  State<HubRefresh> createState() => _HubRefreshState();
}

class _HubRefreshState extends State<HubRefresh> {
  bool _busy = false;

  Future<void> _refresh() async {
    setState(() => _busy = true);
    try {
      await widget.onRefresh();
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Stack(
        children: [
          RefreshIndicator.noSpinner(onRefresh: _refresh, child: widget.child),
          if (_busy)
            const Positioned(top: 12, left: 0, right: 0, child: Center(child: HubLoader(key: Key('pull-refresh-loader'), size: 40))),
        ],
      );
}

/// Kleines Symbol für den Datenstand: aktuell, wird aktualisiert, offline oder Aktualisierung fehlgeschlagen.
/// Details (Stand, Fehler) beim Antippen.
class ReadStatusIcon extends ConsumerWidget {
  final ApiResult<dynamic>? result;
  const ReadStatusIcon({super.key, required this.result});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final r = result;
    final pending = ref.watch(pendingChangesProvider).valueOrNull ?? const <PendingChange>[];
    if (pending.isNotEmpty) return PendingChangesButton(changes: pending);
    if (r == null) return const SizedBox.shrink();
    final scheme = Theme.of(context).colorScheme;
    final at = r.cachedAt == null ? '' : DateFormat('dd.MM. HH:mm', 'de_DE').format(r.cachedAt!.toLocal());
    final stand = at.isEmpty ? '' : ', Stand $at';
    final (IconData icon, Color color, String label) = r.offline
        ? (Icons.cloud_off, scheme.error, 'Offline$stand')
        : r.refreshError != null
            ? (Icons.sync_problem, scheme.error, 'Aktualisierung fehlgeschlagen$stand – ${errorText(r.refreshError!)}')
            : r.refreshing
                ? (Icons.sync, scheme.primary, 'Wird aktualisiert$stand')
                : (Icons.cloud_done_outlined, scheme.onSurfaceVariant, 'Aktuell$stand');
    return Tooltip(
      key: const Key('read-status'),
      message: label,
      triggerMode: TooltipTriggerMode.tap,
      showDuration: const Duration(seconds: 4),
      child: Semantics(
        label: label,
        excludeSemantics: true,
        child: Padding(padding: const EdgeInsets.all(8), child: Icon(icon, size: 20, color: color)),
      ),
    );
  }
}

/// „offline, Stand 14:32“ nur nach einem fehlgeschlagenen Netzversuch.
class OfflineBanner extends StatelessWidget {
  final DateTime? cachedAt;
  const OfflineBanner({super.key, this.cachedAt});

  @override
  Widget build(BuildContext context) {
    final stand = cachedAt == null ? '' : ', Stand ${_time.format(cachedAt!.toLocal())}';
    return _Banner(
      icon: Icons.cloud_off,
      color: Theme.of(context).colorScheme.tertiaryContainer,
      text: 'Offline$stand',
    );
  }
}

/// Eine Quelle (Nextcloud, Home Assistant …) ist nicht erreichbar. Rest der Seite bleibt nutzbar.
class SourceBanner extends StatelessWidget {
  final String source;
  final SourceStatus status;
  final String? error;
  const SourceBanner({super.key, required this.source, required this.status, this.error});

  @override
  Widget build(BuildContext context) {
    if (status == SourceStatus.ok) return const SizedBox.shrink();
    final text = status == SourceStatus.notConfigured
        ? '$source ist noch nicht eingerichtet'
        : '$source gerade nicht erreichbar';
    return _Banner(
      icon: Icons.warning_amber_rounded,
      color: Theme.of(context).colorScheme.errorContainer,
      text: text,
      detail: error,
    );
  }
}

class _Banner extends StatelessWidget {
  final IconData icon;
  final Color color;
  final String text;
  final String? detail;
  const _Banner({required this.icon, required this.color, required this.text, this.detail});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.fromLTRB(16, 8, 16, 0),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(12)),
      child: Row(
        children: [
          Icon(icon, size: 18),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(text),
                if (detail != null && detail!.isNotEmpty)
                  Text(detail!,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodySmall),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Fehler beim Laden der ganzen Seite, mit „Erneut versuchen“.
class ErrorView extends StatelessWidget {
  final Object error;
  final VoidCallback onRetry;
  const ErrorView({super.key, required this.error, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return ListView(
      // scrollbar, damit Pull-to-refresh auch im Fehlerfall geht
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.all(32),
      children: [
        const SizedBox(height: 48),
        Icon(error is OfflineException ? Icons.cloud_off : Icons.error_outline, size: 48),
        const SizedBox(height: 16),
        Text(errorText(error), textAlign: TextAlign.center),
        const SizedBox(height: 16),
        Center(
          child: FilledButton.tonal(onPressed: onRetry, child: const Text('Erneut versuchen')),
        ),
      ],
    );
  }
}

class EmptyHint extends StatelessWidget {
  final IconData icon;
  final String text;
  const EmptyHint({super.key, required this.icon, required this.text});

  @override
  Widget build(BuildContext context) {
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 40, horizontal: 24),
      child: Column(
        children: [
          Icon(icon, size: 40, color: muted),
          const SizedBox(height: 12),
          Text(text, textAlign: TextAlign.center, style: TextStyle(color: muted)),
        ],
      ),
    );
  }
}

/// Karte mit Überschrift für die Heute-Ansicht und Einstellungen.
/// Position einer Karte auf der Seite → Akzentfarbe (Neo-Brutalism: jede Karte eine andere Farbe).
class SectionAccentScope extends InheritedWidget {
  final int index;
  const SectionAccentScope({super.key, required this.index, required super.child});

  static int? maybeOf(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<SectionAccentScope>()?.index;

  @override
  bool updateShouldNotify(SectionAccentScope oldWidget) => oldWidget.index != index;
}

class SectionCard extends StatelessWidget {
  final IconData icon;
  final String title;
  final Widget child;
  final VoidCallback? onTap;
  final Widget? trailing;
  const SectionCard({
    super.key,
    required this.icon,
    required this.title,
    required this.child,
    this.onTap,
    this.trailing,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final style = HubStyle.of(context);
    final label = style.uppercaseTitles ? title.toUpperCase() : title;
    final titleStyle = theme.textTheme.titleMedium?.copyWith(
      letterSpacing: style.uppercaseTitles ? 1.2 : null,
      fontSize: style.uppercaseTitles ? 13 : null,
    );

    if (style.bandHeader) {
      // Neo-Brutalism: farbiger Kopf mit Trennlinie, Inhalt darunter
      final position = SectionAccentScope.maybeOf(context);
      final accent = position != null && style.accents.isNotEmpty
          ? style.accents[position % style.accents.length]
          : style.accentFor(title, theme.colorScheme.primary);
      final onAccent = ThemeData.estimateBrightnessForColor(accent) == Brightness.dark ? Colors.white : Colors.black;
      return HubSurface(
        onTap: onTap,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(
              color: accent,
              padding: const EdgeInsets.fromLTRB(14, 10, 10, 10),
              child: Row(
                children: [
                  Icon(icon, size: 20, color: onAccent),
                  const SizedBox(width: 8),
                  Expanded(child: Text(label, style: titleStyle?.copyWith(color: onAccent))),
                  if (trailing != null) IconTheme.merge(data: IconThemeData(color: onAccent), child: trailing!),
                ],
              ),
            ),
            Container(height: style.borderWidth, color: style.border),
            Padding(padding: const EdgeInsets.fromLTRB(16, 12, 16, 14), child: child),
          ],
        ),
      );
    }

    return HubSurface(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, size: 20, color: theme.colorScheme.primary),
                const SizedBox(width: 8),
                Expanded(child: Text(label, style: titleStyle)),
                if (trailing != null) trailing!,
              ],
            ),
            const SizedBox(height: 10),
            child,
          ],
        ),
      ),
    );
  }
}

String errorText(Object error) => switch (error) {
      ApiException e => e.message,
      OfflineException e => e.toString(),
      _ => 'Unerwarteter Fehler: $error',
    };

void showError(BuildContext context, Object error) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(content: Text(errorText(error))));
}

void showInfo(BuildContext context, String text) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(content: Text(text)));
}

/// Führt eine Schreibaktion aus und zeigt Fehler als Snackbar. Liefert true bei Erfolg.
/// Wie [runAction], für Änderungen, die auch ohne Netz gehen (Einkauf, Aufgaben abhaken):
/// [action] liefert false, wenn die Änderung nur gemerkt wurde – dann ein kurzer Hinweis.
Future<bool> runChange(BuildContext context, Future<bool> Function() action) async {
  var sent = true;
  final ok = await runAction(context, () async => sent = await action());
  if (ok && !sent && context.mounted) showInfo(context, 'Ohne Netz gemerkt – wird gesendet, sobald der Hub erreichbar ist');
  return ok;
}

Future<bool> runAction(BuildContext context, Future<void> Function() action) async {
  try {
    await action();
    return true;
  } catch (e) {
    if (context.mounted) showError(context, e);
    return false;
  }
}

/// Deutsche Tagesüberschrift: „Heute“, „Morgen“, „Mittwoch, 15. Oktober“.
String dayLabel(DateTime day, {DateTime? now}) {
  final n = now ?? DateTime.now();
  final today = DateTime(n.year, n.month, n.day);
  final d = DateTime(day.year, day.month, day.day);
  final diff = d.difference(today).inDays;
  if (diff == 0) return 'Heute';
  if (diff == 1) return 'Morgen';
  if (diff == -1) return 'Gestern';
  return DateFormat('EEEE, d. MMMM', 'de_DE').format(d);
}

String timeLabel(DateTime t) => _time.format(t.toLocal());


/// Statt des Status-Symbols, solange Änderungen warten: Wolke mit Zahl; antippen zeigt die Liste.
class PendingChangesButton extends StatelessWidget {
  final List<PendingChange> changes;
  const PendingChangesButton({super.key, required this.changes});

  @override
  Widget build(BuildContext context) {
    final conflicts = changes.where((c) => c.isConflict).length;
    final scheme = Theme.of(context).colorScheme;
    final label = conflicts > 0
        ? '$conflicts Änderung${conflicts == 1 ? '' : 'en'} abgelehnt'
        : '${changes.length} Änderung${changes.length == 1 ? '' : 'en'} warten auf Netz';
    return IconButton(
      key: const Key('pending-changes'),
      tooltip: label,
      onPressed: () => showModalBottomSheet<void>(
        context: context,
        useSafeArea: true,
        builder: (_) => const PendingChangesSheet(),
      ),
      icon: Badge(
        label: Text('${changes.length}'),
        backgroundColor: conflicts > 0 ? scheme.error : scheme.primary,
        child: Icon(conflicts > 0 ? Icons.sync_problem : Icons.cloud_upload_outlined,
            size: 20, color: conflicts > 0 ? scheme.error : scheme.primary),
      ),
    );
  }
}

/// Liste der gemerkten Änderungen: senden, verwerfen; abgelehnte mit Grund.
class PendingChangesSheet extends ConsumerWidget {
  const PendingChangesSheet({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final changes = ref.watch(pendingChangesProvider).valueOrNull ?? const <PendingChange>[];
    final api = ref.read(apiClientProvider);
    final theme = Theme.of(context);
    if (changes.isEmpty) {
      return const Padding(
        padding: EdgeInsets.all(24),
        child: EmptyHint(icon: Icons.cloud_done_outlined, text: 'Alles gesendet'),
      );
    }
    return ListView(shrinkWrap: true, padding: const EdgeInsets.only(bottom: 16), children: [
      Padding(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
        child: Text('Noch nicht gesendet', style: theme.textTheme.titleMedium),
      ),
      const Padding(
        padding: EdgeInsets.symmetric(horizontal: 16),
        child: Text('Wird automatisch gesendet, sobald der Hub erreichbar ist. Beim Abmelden gehen diese Änderungen verloren.'),
      ),
      for (final c in changes)
        ListTile(
          key: ValueKey('pending-${c.id}'),
          leading: Icon(c.isConflict ? Icons.error_outline : Icons.schedule,
              color: c.isConflict ? theme.colorScheme.error : null),
          title: Text(c.label),
          subtitle: Text(c.isConflict ? 'Abgelehnt: ${c.conflict}' : 'gemerkt ${DateFormat('HH:mm', 'de_DE').format(c.created)}'),
          trailing: IconButton(
            tooltip: c.isConflict ? 'Ausblenden' : 'Verwerfen',
            icon: const Icon(Icons.delete_outline),
            onPressed: () => api.discardPending(c.id),
          ),
        ),
      if (changes.any((c) => !c.isConflict))
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
          child: FilledButton.icon(
            key: const Key('pending-send-now'),
            onPressed: () => api.flushPending(),
            icon: const Icon(Icons.cloud_upload_outlined),
            label: const Text('Jetzt senden'),
          ),
        ),
    ]);
  }
}
