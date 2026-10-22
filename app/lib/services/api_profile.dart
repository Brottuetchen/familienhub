part of 'api_client.dart';

final _avatarCache = <String, Uint8List>{};

/// Profile, avatars and hub images.
mixin ProfileApi on ApiClientBase {
  // ── Profil ─────────────────────────────────────────────────────────────────

  /// Anzeigename (leer = zurück auf den vollen Namen) und Avatar-Farbe (#RRGGBB oder null).
  Future<AppUser> updateProfile({String? displayName, String? avatarColor, bool clearColor = false}) async =>
      AppUser.fromJson(await _send('PATCH', '/api/me/profile', body: {
        if (displayName != null) 'display_name': displayName,
        if (avatarColor != null || clearColor) 'avatar_color': avatarColor,
      }) as Map<String, dynamic>);

  /// Profilbild (JPEG/PNG/WebP, höchstens 512 KB; vorher in der App verkleinern).
  Future<AppUser> uploadAvatar(Uint8List bytes) async =>
      AppUser.fromJson(await _send('PUT', '/api/me/avatar', body: {'image': base64Encode(bytes)}) as Map<String, dynamic>);

  Future<AppUser> deleteAvatar() async => AppUser.fromJson(await _send('DELETE', '/api/me/avatar') as Map<String, dynamic>);

  /// Profilbild laden (angemeldet). Die Version steckt in der URL, daher genügt ein Speicher-Cache.
  Future<Uint8List?> avatarBytes(String url) async {
    final cached = _avatarCache[url];
    if (cached != null) return cached;
    try {
      final res = await _raw('GET', url);
      if (res.statusCode != 200 || !(res.headers['content-type'] ?? '').startsWith('image/')) return null;
      return _avatarCache[url] = res.bodyBytes;
    } catch (_) {
      return null; // offline: Initialen statt Bild
    }
  }

  /// Picture of a plugin's Today card (a hub path below /api/plugins/, loaded with the login). Not cached: the
  /// same path may show something else tomorrow. Null when it cannot be loaded.
  Future<Uint8List?> pluginImageBytes(String path) async {
    if (!path.startsWith('/api/plugins/')) return null;
    try {
      final res = await _raw('GET', path);
      if (res.statusCode != 200 || !(res.headers['content-type'] ?? '').startsWith('image/')) return null;
      return res.bodyBytes;
    } catch (_) {
      return null;
    }
  }

  /// Image from a hub route (for example a plugin that proxies a photo server), loaded with the login. Kept in
  /// memory for this session, the 60 newest images; null when it cannot be loaded (offline, not an image).
  Future<Uint8List?> imageBytes(String path) async {
    final cached = _imageCache.remove(path);
    if (cached != null) return _imageCache[path] = cached; // move to the end: most recently used
    try {
      final res = await _raw('GET', path);
      if (res.statusCode != 200 || !(res.headers['content-type'] ?? '').startsWith('image/')) return null;
      if (_imageCache.length >= 60) _imageCache.remove(_imageCache.keys.first);
      return _imageCache[path] = res.bodyBytes;
    } catch (_) {
      return null;
    }
  }
}
