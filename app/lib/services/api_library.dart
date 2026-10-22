part of 'api_client.dart';

/// Books, films and Paperless documents.
mixin LibraryApi on ApiClientBase {
  // ── Dokumente (Paperless-Plugin) ───────────────────────────────────────────

  Future<Map<String, dynamic>> paperlessAccount() async =>
      await _send('GET', '/api/paperless/account') as Map<String, dynamic>;

  /// Eigenes Paperless-API-Token hinterlegen (der Hub prüft es bei Paperless).
  Future<Map<String, dynamic>> connectPaperless(String token) async =>
      await _send('PUT', '/api/paperless/account', body: {'token': token}) as Map<String, dynamic>;

  Future<void> disconnectPaperless() => _send('DELETE', '/api/paperless/account');

  Future<PaperlessList> paperlessRecent() async =>
      PaperlessList.fromJson(await _send('GET', '/api/paperless/recent') as Map<String, dynamic>);

  Future<PaperlessList> paperlessSearch(String query) async {
    final q = Uri(queryParameters: {'q': query}).query;
    return PaperlessList.fromJson(await _send('GET', '/api/paperless/search?$q') as Map<String, dynamic>);
  }

  Future<PaperlessList> paperlessDeadlines() async =>
      PaperlessList.fromJson(await _send('GET', '/api/paperless/deadlines') as Map<String, dynamic>);

  /// Frist als eigene Erinnerung (am Fristtag 9 Uhr). true = neu angelegt, false = gab es schon.
  Future<bool> paperlessRemind(int id) async =>
      ((await _send('POST', '/api/paperless/deadlines/$id/remind')) as Map<String, dynamic>)['created'] == true;

  /// Vorschaubild über den Hub (angemeldet), zwischengespeichert wie Profilbilder.
  /// Sibling mixins do not see each other's methods, so this goes through [ApiClient].
  Future<Uint8List?> paperlessThumb(String path) => (this as ApiClient).avatarBytes(path);

  // ── Filme & Serien (Seerr) ─────────────────────────────────────────────────

  Future<MediaList<MediaItem>> searchMedia(String query) async {
    final q = Uri(queryParameters: {'q': query}).query;
    return MediaList.fromJson(await _send('GET', '/api/media/search?$q') as Map<String, dynamic>, MediaItem.fromJson);
  }

  Future<MediaList<MediaRequestItem>> mediaRequests() async =>
      MediaList.fromJson(await _send('GET', '/api/media/requests') as Map<String, dynamic>, MediaRequestItem.fromJson);

  /// Wunsch anlegen; liefert den Stand als Text (z. B. „Wartet auf Freigabe“).
  Future<String> requestMedia(MediaItem item) async {
    final json = await _send('POST', '/api/media/requests',
        body: {'media_type': item.kind.api, 'tmdb_id': item.tmdbId}) as Map<String, dynamic>;
    return (json['status_label'] as String?) ?? l10n.requested;
  }

  Future<void> cancelMediaRequest(int id) => _send('DELETE', '/api/media/requests/$id');

  /// Shelves of books that exist in German (Open Library), requestable like search results.
  Future<SourceResult<BookResult>> discoverBooks(String shelf) async => SourceResult.fromJson(
      await _send('GET', '/api/books/discover?shelf=${Uri.encodeQueryComponent(shelf)}') as Map<String, dynamic>, BookResult.fromJson);

  Future<SourceResult<BookResult>> searchBooks(String query, {BookKind? kind}) async {
    final q = Uri(queryParameters: {'q': query, if (kind != null) 'book_type': kind.api}).query;
    return SourceResult.fromJson(
        await _send('GET', '/api/books/search?$q') as Map<String, dynamic>, BookResult.fromJson);
  }

  Future<ApiResult<SourceResult<BookRequest>>> bookRequests() => _cachedGet('/api/books/requests', 'books',
      (j) => SourceResult.fromJson(j as Map<String, dynamic>, BookRequest.fromJson));

  /// Wunsch anlegen; liefert Hinweise von Shelfarr (z. B. „wird im Hintergrund angelegt“).
  Future<List<String>> requestBook(BookResult book, BookKind kind) async {
    final json = await _send('POST', '/api/books/requests', body: {
      'work_id': book.workId,
      'book_type': kind.api,
      'title': book.title,
      if (book.author != null) 'author': book.author,
      if (book.coverUrl != null) 'cover_url': book.coverUrl,
      if (book.year != null) 'year': book.year,
    }) as Map<String, dynamic>;
    return [
      if (json['queued'] == true) l10n.creatingInBackground,
      ...((json['warnings'] as List?) ?? const []).map((w) => '$w'),
    ];
  }

  Future<void> cancelBookRequest(int id) => _send('DELETE', '/api/books/requests/$id');
}
