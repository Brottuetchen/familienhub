import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/media.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';

final mediaRequestsProvider =
    FutureProvider.autoDispose<MediaList<MediaRequestItem>>((ref) => ref.watch(apiClientProvider).mediaRequests());

/// Filme und Serien wünschen (Seerr), als eigener Seerr-Nutzer. Gesucht wird nur auf Enter.
class MediaScreen extends ConsumerStatefulWidget {
  const MediaScreen({super.key});

  @override
  ConsumerState<MediaScreen> createState() => _MediaScreenState();
}

class _MediaScreenState extends ConsumerState<MediaScreen> {
  final _query = TextEditingController();
  MediaKind? _kind; // null = alles
  bool _searching = false;
  MediaList<MediaItem>? _results;
  final _requested = <String, String>{}; // "movie:603" → Stand nach dem Wünschen

  @override
  void dispose() {
    _query.dispose();
    super.dispose();
  }

  Future<void> _search() async {
    if (_searching) return;
    final q = _query.text.trim();
    if (q.length < 2) {
      setState(() => _results = null);
      return;
    }
    FocusScope.of(context).unfocus();
    setState(() => _searching = true);
    try {
      final r = await ref.read(apiClientProvider).searchMedia(q);
      if (mounted) setState(() => _results = r);
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _searching = false);
    }
  }

  Future<void> _request(MediaItem item) async {
    try {
      final label = await ref.read(apiClientProvider).requestMedia(item);
      if (!mounted) return;
      setState(() => _requested['${item.kind.api}:${item.tmdbId}'] = label);
      showInfo(context, '${item.kind.label} „${item.title}“ gewünscht · $label');
      ref.invalidate(mediaRequestsProvider);
    } catch (e) {
      if (mounted) showError(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Filme & Serien')),
      body: Column(children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
          child: SegmentedButton<MediaKind?>(
            segments: const [
              ButtonSegment(value: null, label: Text('Alles')),
              ButtonSegment(value: MediaKind.movie, label: Text('Filme'), icon: Icon(Icons.movie_outlined)),
              ButtonSegment(value: MediaKind.tv, label: Text('Serien'), icon: Icon(Icons.tv)),
            ],
            selected: {_kind},
            onSelectionChanged: (s) => setState(() => _kind = s.first), // filtert nur
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: TextField(
            key: const Key('media-search'),
            controller: _query,
            textInputAction: TextInputAction.search,
            onChanged: (_) => setState(() {}),
            onSubmitted: (_) => _search(),
            decoration: InputDecoration(
              hintText: 'Film oder Serie',
              helperText: 'Suchen mit Enter',
              prefixIcon: const Icon(Icons.search),
              suffixIcon: _query.text.isEmpty
                  ? null
                  : Row(mainAxisSize: MainAxisSize.min, children: [
                      IconButton(
                        tooltip: 'Leeren',
                        icon: const Icon(Icons.clear),
                        onPressed: () => setState(() {
                          _query.clear();
                          _results = null;
                        }),
                      ),
                      IconButton(
                        key: const Key('media-search-go'),
                        tooltip: 'Suchen',
                        icon: const Icon(Icons.arrow_forward),
                        onPressed: _searching ? null : _search,
                      ),
                    ]),
            ),
          ),
        ),
        if (_searching) const Padding(padding: EdgeInsets.all(12), child: HubLoader(size: 32)),
        Expanded(child: _results == null ? _MyMediaRequests(kind: _kind) : _resultList(_results!)),
      ]),
    );
  }

  Widget _resultList(MediaList<MediaItem> r) {
    if (!r.ok) return ListView(children: [_StatusHint(list: r)]);
    final shown = [for (final m in r.items) if (_kind == null || m.kind == _kind) m];
    if (shown.isEmpty) return const EmptyHint(icon: Icons.search_off, text: 'Nichts gefunden');
    return ListView.builder(
      itemCount: shown.length,
      itemBuilder: (context, i) {
        final m = shown[i];
        final key = '${m.kind.api}:${m.tmdbId}';
        final justRequested = _requested[key];
        final Widget trailing;
        if (justRequested != null) {
          trailing = _StatusChip(label: justRequested, done: true, key: ValueKey('media-done-$key'));
        } else if (!m.requestable) {
          trailing = _StatusChip(label: m.statusLabel ?? 'Vorhanden', done: m.statusLabel == 'Verfügbar');
        } else if (!ref.watch(canActProvider)) {
          trailing = const SizedBox.shrink(); // Gäste suchen nur, wünschen ab Kind
        } else {
          trailing = FilledButton.tonal(
            key: ValueKey('media-request-$key'),
            onPressed: () => _request(m),
            child: const Text('Wünschen'),
          );
        }
        return ListTile(
          leading: _Poster(url: m.poster, kind: m.kind),
          title: Text(m.title, maxLines: 2, overflow: TextOverflow.ellipsis),
          subtitle: Text(
            [m.kind.label, if (m.year != null) '${m.year}', if (m.overview.isNotEmpty) m.overview].join(' · '),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
          trailing: trailing,
        );
      },
    );
  }
}

class _StatusHint extends StatelessWidget {
  final MediaList list;
  const _StatusHint({required this.list});

  @override
  Widget build(BuildContext context) => switch (list.status) {
        'not_configured' => const EmptyHint(icon: Icons.movie_outlined, text: 'Seerr ist noch nicht eingerichtet'),
        'no_account' => const EmptyHint(
            icon: Icons.person_off_outlined,
            text: 'Für dich gibt es noch keinen Seerr-Zugang.\nEinmal bei Seerr mit deinem Jellyfin-Konto anmelden, dann klappt es hier.'),
        _ => EmptyHint(icon: Icons.cloud_off, text: 'Seerr gerade nicht erreichbar${list.error == null ? '' : '\n${list.error}'}'),
      };
}

class _StatusChip extends StatelessWidget {
  final String label;
  final bool done;
  final bool problem;
  const _StatusChip({super.key, required this.label, this.done = false, this.problem = false});

  @override
  Widget build(BuildContext context) => Chip(
        label: Text(label),
        visualDensity: VisualDensity.compact,
        backgroundColor: done
            ? Colors.green.withValues(alpha: 0.25)
            : problem
                ? Theme.of(context).colorScheme.errorContainer
                : null,
      );
}

class _Poster extends StatelessWidget {
  final String? url;
  final MediaKind kind;
  const _Poster({this.url, required this.kind});

  @override
  Widget build(BuildContext context) {
    const size = Size(44, 66);
    final fallback = Container(
      width: size.width,
      height: size.height,
      color: Theme.of(context).colorScheme.surfaceContainerHigh,
      child: Icon(kind == MediaKind.tv ? Icons.tv : Icons.movie_outlined, size: 20),
    );
    if (url == null || url!.isEmpty) return fallback;
    return ClipRRect(
      borderRadius: BorderRadius.circular(4),
      child: Image.network(url!, width: size.width, height: size.height, fit: BoxFit.cover,
          errorBuilder: (_, __, ___) => fallback),
    );
  }
}

class _MyMediaRequests extends ConsumerWidget {
  final MediaKind? kind;
  const _MyMediaRequests({this.kind});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(mediaRequestsProvider);
    Future<void> refresh() => ref.refresh(mediaRequestsProvider.future);
    return HubRefresh(
      onRefresh: refresh,
      child: async.when(
        loading: () => const Center(child: HubLoader()),
        error: (e, _) => ErrorView(error: e, onRetry: refresh),
        data: (list) {
          if (!list.ok) return ListView(children: [_StatusHint(list: list)]);
          final shown = [for (final r in list.items) if (kind == null || r.kind == kind) r];
          return ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
                child: Text('Meine Wünsche', style: Theme.of(context).textTheme.titleMedium),
              ),
              if (shown.isEmpty)
                const EmptyHint(icon: Icons.local_movies_outlined, text: 'Noch nichts gewünscht. Oben suchen.'),
              for (final r in shown)
                ListTile(
                  key: ValueKey('media-req-${r.id}'),
                  leading: _Poster(url: r.poster, kind: r.kind),
                  title: Text(r.title, maxLines: 2, overflow: TextOverflow.ellipsis),
                  subtitle: Text([r.kind.label, if (r.year != null) '${r.year}'].join(' · ')),
                  trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                    _StatusChip(label: r.statusLabel, done: r.available, problem: r.isProblem),
                    if (r.canCancel)
                      IconButton(
                        tooltip: 'Wunsch zurückziehen',
                        icon: const Icon(Icons.close),
                        onPressed: () async {
                          if (await runAction(context, () => ref.read(apiClientProvider).cancelMediaRequest(r.id))) {
                            ref.invalidate(mediaRequestsProvider);
                          }
                        },
                      ),
                  ]),
                ),
            ],
          );
        },
      ),
    );
  }
}
