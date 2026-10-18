import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../models/books.dart';
import '../../models/common.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';

final bookRequestsProvider = FutureProvider.autoDispose<ApiResult<SourceResult<BookRequest>>>(
    (ref) => ref.watch(apiClientProvider).bookRequests());

/// Bücher und Hörbücher wünschen (Shelfarr). Immer auf Deutsch.
///
/// Gesucht wird nur auf Enter (oder Lupe): jede Suche fragt über Shelfarr Google Books, dessen
/// Kontingent knapp ist. E-Book/Hörbuch filtert die vorhandenen Treffer, ohne neu zu suchen.
class BooksScreen extends ConsumerStatefulWidget {
  const BooksScreen({super.key});

  @override
  ConsumerState<BooksScreen> createState() => _BooksScreenState();
}

class _BooksScreenState extends ConsumerState<BooksScreen> {
  static const _kindKey = 'books_kind';
  final _query = TextEditingController();
  BookKind _kind = BookKind.ebook;
  bool _searching = false;
  bool _tooShort = false;
  SourceResult<BookResult>? _results;
  final _requested = <String>{};

  @override
  void initState() {
    super.initState();
    // Zuletzt gewählte Art merken (die eine liest E-Books, der andere hört Hörbücher)
    SharedPreferences.getInstance().then((p) {
      final k = BookKind.fromApi(p.getString(_kindKey));
      if (k != null && mounted) setState(() => _kind = k);
    });
  }

  @override
  void dispose() {
    _query.dispose();
    super.dispose();
  }

  Future<void> _search() async {
    if (_searching) return;
    final q = _query.text.trim();
    if (q.length < 3) { // wie das Backend: kürzere Suchen bringen bei Shelfarr nur Fehler
      setState(() { _results = null; _tooShort = q.isNotEmpty; });
      return;
    }
    FocusScope.of(context).unfocus();
    setState(() { _searching = true; _tooShort = false; });
    try {
      final r = await ref.read(apiClientProvider).searchBooks(q);
      if (mounted) setState(() => _results = r);
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _searching = false);
    }
  }

  Future<void> _setKind(BookKind k) async {
    setState(() => _kind = k); // filtert nur, keine neue Suche
    (await SharedPreferences.getInstance()).setString(_kindKey, k.api);
  }

  Future<void> _request(BookResult book) async {
    try {
      final hints = await ref.read(apiClientProvider).requestBook(book, _kind);
      if (!mounted) return;
      setState(() => _requested.add('${_kind.api}:${book.workId}'));
      showInfo(context, ['${_kind.label} „${book.title}“ gewünscht', ...hints].join(' · '));
      ref.invalidate(bookRequestsProvider);
    } catch (e) {
      if (mounted) showError(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Bücher & Hörbücher')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
            child: SegmentedButton<BookKind>(
              segments: [
                for (final k in BookKind.values)
                  ButtonSegment(
                    value: k,
                    label: Text(k.label),
                    icon: Icon(k == BookKind.ebook ? Icons.menu_book : Icons.headphones),
                  ),
              ],
              selected: {_kind},
              onSelectionChanged: (s) => _setKind(s.first),
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: TextField(
              key: const Key('book-search'),
              controller: _query,
              onChanged: (_) => setState(() => _tooShort = false), // nur Knöpfe aktualisieren, nicht suchen
              onSubmitted: (_) => _search(),
              textInputAction: TextInputAction.search,
              decoration: InputDecoration(
                hintText: 'Titel oder Autor',
                prefixIcon: const Icon(Icons.search),
                helperText: _tooShort ? 'Mindestens 3 Zeichen' : 'Suchen mit Enter',
                suffixIcon: _query.text.isEmpty
                    ? null
                    : Row(mainAxisSize: MainAxisSize.min, children: [
                        IconButton(
                          tooltip: 'Leeren',
                          icon: const Icon(Icons.clear),
                          onPressed: () => setState(() {
                            _query.clear();
                            _results = null;
                            _tooShort = false;
                          }),
                        ),
                        IconButton(
                          key: const Key('book-search-go'),
                          tooltip: 'Suchen',
                          icon: const Icon(Icons.arrow_forward),
                          onPressed: _searching ? null : _search,
                        ),
                      ]),
              ),
            ),
          ),
          if (_searching) const Padding(padding: EdgeInsets.all(12), child: HubLoader(size: 32)),
          Expanded(child: _results == null ? const _MyRequests() : _resultList(_results!)),
        ],
      ),
    );
  }

  Widget _resultList(SourceResult<BookResult> r) {
    if (!r.isOk) return ListView(children: [SourceBanner(source: 'Shelfarr', status: r.status, error: r.error)]);
    final shown = [for (final b in r.items) if (b.kinds.isEmpty || b.kinds.contains(_kind)) b];
    if (shown.isEmpty) {
      return EmptyHint(
        icon: Icons.search_off,
        text: r.items.isEmpty ? 'Nichts gefunden' : 'Nichts als ${_kind.label} gefunden',
      );
    }
    // Schon gewünscht (gleicher Titel und gleiche Art): kein zweiter Wunsch
    final mine = ref.watch(bookRequestsProvider).valueOrNull?.data.items ?? const <BookRequest>[];
    final wished = {for (final w in mine) if (w.kind != null) '${w.kind!.api}:${w.title.toLowerCase()}'};
    final canWish = ref.watch(canActProvider); // Gäste suchen nur, wünschen ab Kind
    return ListView.builder(
      itemCount: shown.length,
      itemBuilder: (context, i) {
        final b = shown[i];
        final done = _requested.contains('${_kind.api}:${b.workId}') ||
            wished.contains('${_kind.api}:${b.title.toLowerCase()}');
        final sub = [
          if (b.author != null) b.author!,
          if (b.year != null) '${b.year}',
          if (b.series != null) b.series!,
        ].join(' · ');
        return ListTile(
          leading: _Cover(url: b.coverUrl),
          title: Text(b.title, maxLines: 2, overflow: TextOverflow.ellipsis),
          subtitle: sub.isEmpty ? null : Text(sub, maxLines: 1, overflow: TextOverflow.ellipsis),
          trailing: done
              ? Tooltip(
                  message: 'Schon gewünscht',
                  child: Icon(Icons.check_circle, key: ValueKey('book-done-${b.workId}'), color: Colors.green),
                )
              : !canWish ? null : FilledButton.tonal(
                  key: ValueKey('book-request-${b.workId}'),
                  onPressed: () => _request(b),
                  child: const Text('Wünschen'),
                ),
        );
      },
    );
  }
}

class _Cover extends StatelessWidget {
  final String? url;
  const _Cover({this.url});

  @override
  Widget build(BuildContext context) {
    const size = Size(40, 58);
    final fallback = Container(
      width: size.width,
      height: size.height,
      color: Theme.of(context).colorScheme.surfaceContainerHigh,
      child: const Icon(Icons.book_outlined, size: 20),
    );
    if (url == null || url!.isEmpty) return fallback;
    return ClipRRect(
      borderRadius: BorderRadius.circular(4),
      child: Image.network(url!, width: size.width, height: size.height, fit: BoxFit.cover,
          errorBuilder: (_, __, ___) => fallback),
    );
  }
}

class _MyRequests extends ConsumerWidget {
  const _MyRequests();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(bookRequestsProvider);
    Future<void> refresh() => ref.refresh(bookRequestsProvider.future);
    return HubRefresh(
      onRefresh: refresh,
      child: async.when(
        loading: () => const Center(child: HubLoader()),
        error: (e, _) => ErrorView(error: e, onRetry: refresh),
        data: (result) {
          final data = result.data;
          return ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            children: [
              if (result.fromCache) OfflineBanner(cachedAt: result.cachedAt),
              SourceBanner(source: 'Shelfarr', status: data.status, error: data.error),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
                child: Text('Meine Wünsche', style: Theme.of(context).textTheme.titleMedium),
              ),
              if (data.isOk && data.items.isEmpty)
                const EmptyHint(icon: Icons.auto_stories_outlined, text: 'Noch nichts gewünscht. Oben suchen.'),
              for (final r in data.items)
                ListTile(
                  leading: Icon(r.kind == BookKind.audiobook ? Icons.headphones : Icons.menu_book),
                  title: Text(r.title),
                  subtitle: Text([if (r.author != null) r.author!, if (r.issue != null) r.issue!].join(' · ')),
                  trailing: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Chip(
                        label: Text(r.statusLabel),
                        visualDensity: VisualDensity.compact,
                        backgroundColor: r.isDone
                            ? Colors.green.withValues(alpha: 0.25)
                            : r.isProblem
                                ? Theme.of(context).colorScheme.errorContainer
                                : null,
                      ),
                      if (r.canCancel)
                        IconButton(
                          tooltip: 'Wunsch zurückziehen',
                          icon: const Icon(Icons.close),
                          onPressed: () async {
                            if (await runAction(context, () => ref.read(apiClientProvider).cancelBookRequest(r.id))) {
                              ref.invalidate(bookRequestsProvider);
                            }
                          },
                        ),
                    ],
                  ),
                ),
            ],
          );
        },
      ),
    );
  }
}
