part of 'api_client.dart';

/// Setup, invites, administration, backup, themes, plugins and the store.
mixin AdminApi on ApiClientBase {
  Future<List<ServiceKeyInfo>> serviceKeys() async =>
      _maps(await _send('GET', '/api/admin/service-keys')).map(ServiceKeyInfo.fromJson).toList();

  Future<ServiceKeyInfo> createServiceKey(String name) async => ServiceKeyInfo.fromJson(
      await _send('POST', '/api/admin/service-keys', body: {'name': name}) as Map<String, dynamic>);

  Future<void> revokeServiceKey(int id) => _send('DELETE', '/api/admin/service-keys/$id');

  // ── Zugänge für Assistenten ────────────────────────────────────────────────

  Future<List<ApiTokenInfo>> apiTokens() async =>
      _maps(await _send('GET', '/api/auth/api-tokens')).map(ApiTokenInfo.fromJson).toList();

  /// Liefert den Schlüssel inklusive Klartext (nur dieses eine Mal).
  /// [scopes] limits the key to the given scopes or presets (`voice`); without it the key is unrestricted.
  Future<ApiTokenInfo> createApiToken(String name, {List<String>? scopes}) async => ApiTokenInfo.fromJson(
      await _send('POST', '/api/auth/api-tokens', body: {'name': name, if (scopes != null) 'scopes': scopes})
          as Map<String, dynamic>);

  Future<void> revokeApiToken(int id) => _send('DELETE', '/api/auth/api-tokens/$id');

  // ── Ersteinrichtung (#4) ───────────────────────────────────────────────────

  Future<SetupStatus> setupStatus({String? baseUrl}) async =>
      SetupStatus.fromJson(await _send('GET', '/api/setup/status', auth: false, baseUrl: baseUrl) as Map<String, dynamic>);

  /// Legt das erste Admin-Konto an (Einrichtungscode aus dem Server-Log, falls der Server ihn verlangt) und meldet es an.
  Future<AppUser> createFirstAdmin({
    String? code,
    required String username,
    required String email,
    required String password,
    String? displayName,
  }) =>
      _authenticate('/api/setup/admin', {
        if (code != null && code.isNotEmpty) 'code': code,
        'username': username,
        'email': email,
        'password': password,
        if (displayName != null && displayName.isNotEmpty) 'display_name': displayName,
        'client': 'app',
      });

  /// „Verbindung testen“ mit den eingegebenen Werten (leeres Geheimnis = gespeicherten Wert nutzen).
  Future<ConnectionResult> testPlugin(String pluginId, Map<String, String> values) async => ConnectionResult.fromJson(
      await _send('POST', '/api/admin/plugins/${Uri.encodeComponent(pluginId)}/test', body: {'values': values})
          as Map<String, dynamic>);

  Future<({String appName, String timezone})> coreSettings() async {
    final j = await _send('GET', '/api/admin/core') as Map<String, dynamic>;
    return (appName: j['app_name'] as String, timezone: j['timezone'] as String);
  }

  Future<void> saveCoreSettings({required String appName, required String timezone}) =>
      _send('PUT', '/api/admin/core', body: {'app_name': appName, 'timezone': timezone});

  // ── Rückmeldung und App-Fehler ────────────────────────────────────────────

  /// Rückmeldung an die Verwaltung der eigenen Familie.
  Future<void> sendFeedback({required String text, String? area}) => _send('POST', '/api/feedback',
      body: {'text': text, if (area != null) 'area': area, 'app_version': appVersion, 'platform': appPlatform});

  Future<List<Map<String, dynamic>>> adminFeedback() async =>
      (((await _send('GET', '/api/admin/feedback')) as Map)['items'] as List).whereType<Map<String, dynamic>>().toList();

  Future<void> markFeedbackDone(int id) => _send('POST', '/api/admin/feedback/$id/done');

  /// Nur angemeldet; Fehler beim Melden werden geschluckt (der Bericht darf nichts kaputt machen).
  Future<void> reportClientError({required String message, String? stack}) async {
    if (_ended || await store.accessToken() == null) return;
    await _send('POST', '/api/client-errors', body: {
      'message': message.length > 2000 ? message.substring(0, 2000) : message,
      if (stack != null) 'stack': stack.length > 4000 ? stack.substring(0, 4000) : stack,
      'app_version': appVersion,
      'platform': appPlatform,
    });
  }

  // ── Einladungen ───────────────────────────────────────────────────────────

  Future<InviteInfo> createInvite({required String displayName, required String email, String role = 'partner'}) async =>
      InviteInfo.fromJson(await _send('POST', '/api/admin/invites',
          body: {'display_name': displayName, 'email': email, 'role': role}) as Map<String, dynamic>);

  Future<List<InviteInfo>> invites() async => (((await _send('GET', '/api/admin/invites')) as Map)['items'] as List)
      .whereType<Map<String, dynamic>>()
      .map(InviteInfo.fromJson)
      .toList();

  Future<InviteInfo> renewInvite(int id) async =>
      InviteInfo.fromJson(await _send('POST', '/api/admin/invites/$id/renew') as Map<String, dynamic>);

  Future<void> revokeInvite(int id) => _send('DELETE', '/api/admin/invites/$id');

  /// Einladungscode einlösen, eigenes Passwort setzen und anmelden.
  Future<AppUser> acceptInvite({required String code, required String password}) =>
      _authenticate('/api/invites/accept', {'code': code, 'password': password, 'client': 'app'});

  // ── Verwaltung (nur Admins) ────────────────────────────────────────────────

  Future<AdminOverview> adminOverview() async =>
      AdminOverview.fromJson(await _send('GET', '/api/admin/overview') as Map<String, dynamic>);

  Future<List<AdminUser>> adminUsers() async => ((await _send('GET', '/api/admin/users')) as List)
      .whereType<Map<String, dynamic>>()
      .map(AdminUser.fromJson)
      .toList();

  Future<void> updateAdminUser(int id, {String? role, bool? active}) => _send('PATCH', '/api/auth/users/$id', body: {
        if (role != null) 'role': role,
        if (active != null) 'is_active': active,
      });

  Future<void> createAdminUser({
    required String username,
    required String email,
    required String password,
    String? fullName,
    String role = 'partner',
  }) =>
      _send('POST', '/api/auth/users', body: {
        'username': username,
        'email': email,
        'password': password,
        if (fullName != null && fullName.isNotEmpty) 'full_name': fullName,
        'role': role,
      });

  Future<HouseChoices> houseChoices() async =>
      HouseChoices.fromJson(await _send('GET', '/api/admin/house/entities') as Map<String, dynamic>);

  Future<void> saveHouseSelection({required List<String> display, required List<String> control}) =>
      saveAdminSettings({'HA_HOUSE_ENTITIES': display.join(','), 'HA_HOUSE_WRITE_ENTITIES': control.join(',')});

  Future<List<LogEntry>> adminLog() async => (((await _send('GET', '/api/admin/log')) as Map)['items'] as List)
      .whereType<Map<String, dynamic>>()
      .map(LogEntry.fromJson)
      .toList();

  // ── Admin: backup and update notice ────────────────────────────────────────

  Future<BackupInfo> backupInfo() async =>
      BackupInfo.fromJson(await _send('GET', '/api/admin/backup') as Map<String, dynamic>);

  Future<BackupResult> createBackup() async => BackupResult.fromJson(
      await _send('POST', '/api/admin/backup', body: {'include_keys': true}, timeout: const Duration(minutes: 5))
          as Map<String, dynamic>);

  Future<BackupInfo> saveBackupSettings({required bool auto, required int keep}) async => BackupInfo.fromJson(
      await _send('PUT', '/api/admin/backup/settings', body: {'auto': auto, 'keep': keep}) as Map<String, dynamic>);

  Future<BackupResult> deleteBackup(String name) async => BackupResult.fromJson(
      await _send('DELETE', '/api/admin/backup/${Uri.encodeComponent(name)}') as Map<String, dynamic>);

  /// Single-use, short-lived address of a fresh backup file; open it in the browser to save it.
  Future<Uri> backupDownloadUri() async {
    final j = await _send('POST', '/api/admin/backup/download-link', body: {'include_keys': true})
        as Map<String, dynamic>;
    return _uri(j['path'] as String);
  }

  Future<BackupResult> inspectBackup(String name) async => BackupResult.fromJson(
      await _send('POST', '/api/admin/backup/${Uri.encodeComponent(name)}/inspect') as Map<String, dynamic>);

  Future<BackupResult> restoreBackup(String name) async => BackupResult.fromJson(await _send(
          'POST', '/api/admin/backup/${Uri.encodeComponent(name)}/restore',
          body: {'confirm': true}, timeout: const Duration(minutes: 10))
      as Map<String, dynamic>);

  Future<UpdateInfo> updateInfo() async =>
      UpdateInfo.fromJson(await _send('GET', '/api/admin/update') as Map<String, dynamic>);

  Future<UpdateInfo> saveUpdateSettings({required bool enabled, required String repo}) async => UpdateInfo.fromJson(
      await _send('PUT', '/api/admin/update/settings', body: {'enabled': enabled, 'repo': repo})
          as Map<String, dynamic>);

  // ── Darstellung ────────────────────────────────────────────────────────────

  Future<List<ThemeSpec>> themes() async {
    final json = await _send('GET', '/api/themes') as Map<String, dynamic>;
    return _maps(json['items']).map(ThemeSpec.fromJson).toList();
  }

  /// Nur Admins: Theme aus GitHub installieren.
  Future<ThemeSpec> installTheme(String url) async =>
      ThemeSpec.fromJson(await _send('POST', '/api/themes', body: {'url': url}) as Map<String, dynamic>);

  Future<void> deleteTheme(String id) => _send('DELETE', '/api/themes/${Uri.encodeComponent(id)}');

  // ── Admin: install plugins from GitHub ─────────────────────────────────────

  Future<PluginInstallState> pluginInstallState() async =>
      PluginInstallState.fromJson(await _send('GET', '/api/plugins/installed') as Map<String, dynamic>);

  /// Link → manifest, commit and settings form. Nothing is installed.
  Future<PluginPreview> inspectPlugin(String url) async => PluginPreview.fromJson(
      await _send('POST', '/api/plugins/inspect', body: {'url': url}, timeout: const Duration(seconds: 60))
          as Map<String, dynamic>);

  /// Downloads and installs exactly [sha]; takes a while (pip), hence the long timeout.
  Future<PluginInstallResult> installPlugin(String url, String sha, Map<String, String> settings) async =>
      PluginInstallResult.fromJson(await _send('POST', '/api/plugins/install',
          body: {'url': url, 'sha': sha, 'settings': settings}, timeout: const Duration(minutes: 6)) as Map<String, dynamic>);

  /// Returns whether the server needs a restart to forget the plugin completely.
  Future<bool> removePlugin(String id) async =>
      ((await _send('DELETE', '/api/plugins/${Uri.encodeComponent(id)}', timeout: const Duration(minutes: 1)))
          as Map<String, dynamic>)['restart_required'] == true;

  // ── Admin: plugin and theme store (docs/store.md) ──────────────────────────

  /// Entries of all store sources; [refresh] skips the server's short cache.
  Future<StoreListing> storeListing({bool refresh = false}) async => StoreListing.fromJson(
      await _send('GET', '/api/admin/store${refresh ? '?refresh=true' : ''}', timeout: const Duration(seconds: 45))
          as Map<String, dynamic>);

  Map<String, dynamic> _storeRef(StoreItem item) => {'source': item.source, 'type': item.type, 'id': item.id};

  /// Plugin entry → the same preview as a pasted link, but at the commit the index pins.
  Future<PluginPreview> storeInspectPlugin(StoreItem item) async => PluginPreview.fromJson(
      await _send('POST', '/api/admin/store/inspect', body: _storeRef(item), timeout: const Duration(seconds: 60))
          as Map<String, dynamic>);

  Future<StoreDetails> storeDetails(StoreItem item) async => StoreDetails.fromJson(
      await _send('POST', '/api/admin/store/inspect', body: _storeRef(item), timeout: const Duration(seconds: 60))
          as Map<String, dynamic>);

  /// Install or update exactly the commit [sha] that the admin reviewed.
  Future<Map<String, dynamic>> storeInstall(StoreItem item, String sha,
          {Map<String, String> settings = const {}, bool acknowledgeUnverified = false}) async =>
      await _send('POST', '/api/admin/store/install',
          body: {
            ..._storeRef(item),
            'sha': sha,
            'settings': settings,
            'acknowledge_unverified': acknowledgeUnverified,
          },
          timeout: const Duration(minutes: 6)) as Map<String, dynamic>;

  Future<StoreSource> addStoreSource(String url) async => StoreSource.fromJson(
      await _send('POST', '/api/admin/store/sources', body: {'url': url, 'acknowledge': true},
          timeout: const Duration(seconds: 45)) as Map<String, dynamic>);

  Future<void> removeStoreSource(int id) => _send('DELETE', '/api/admin/store/sources/$id');

  /// Screenshot through the hub (the app never contacts GitHub itself); null if it cannot be loaded.
  /// Same cache as profile pictures. Sibling mixins do not see each other's methods, so this goes through [ApiClient].
  Future<Uint8List?> storeScreenshot(String path) => (this as ApiClient).avatarBytes(path);

  // ── Admin: Plugins & Zugänge ───────────────────────────────────────────────

  // ── Calendar subscriptions (ICS, admin) ────────────────────────────────────

  Future<List<({String name, String url})>> icsFeeds() async =>
      _maps(((await _send('GET', '/api/admin/ics')) as Map<String, dynamic>)['feeds'])
          .map((f) => (name: f['name'] as String, url: f['url'] as String))
          .toList();

  Future<void> saveIcsFeeds(List<({String name, String url})> feeds) =>
      _send('PUT', '/api/admin/ics', body: {'feeds': [for (final f in feeds) {'name': f.name, 'url': f.url}]});

  /// Checks a link before adding it: {ok, error, events, sample}.
  Future<Map<String, dynamic>> probeIcs(String url) async =>
      (await _send('POST', '/api/admin/ics/test', body: {'url': url})) as Map<String, dynamic>;

  Future<List<SourceArea>> adminSources() async => _maps(
          ((await _send('GET', '/api/admin/sources')) as Map<String, dynamic>)['areas'])
      .map(SourceArea.fromJson)
      .toList();

  Future<void> setSources(String area, List<String> selected) =>
      _send('PUT', '/api/admin/sources', body: {'area': area, 'selected': selected});

  /// Where Cookidoo/Mealie recipe ingredients go: `merge` (our list) or `source` (the recipe source's own list).
  Future<void> setRecipeIngredients(String mode) =>
      _send('PUT', '/api/admin/recipe-ingredients', body: {'mode': mode});

  /// End of the setup wizard: the server switches off active plugins that were neither chosen as a source nor
  /// set up (`keep`). Returns the ids it disabled.
  Future<List<String>> finishSetup(List<String> keep) async {
    final json = await _send('POST', '/api/admin/setup/finish', body: {'keep': keep}) as Map<String, dynamic>;
    return [for (final id in (json['disabled'] as List? ?? const [])) '$id'];
  }

  Future<List<AdminPlugin>> adminPlugins() async =>
      _maps(await _send('GET', '/api/admin/settings')).map(AdminPlugin.fromJson).toList();

  /// Leere Geheimnisse lässt das Backend unverändert.
  Future<void> saveAdminSettings(Map<String, String> values) =>
      _send('PUT', '/api/admin/settings', body: {'values': values});

  Future<AdminPlugin> setPluginEnabled(String id, bool enabled) async => AdminPlugin.fromJson(
      await _send('PUT', '/api/admin/plugins/${Uri.encodeComponent(id)}', body: {'enabled': enabled})
          as Map<String, dynamic>);
}
