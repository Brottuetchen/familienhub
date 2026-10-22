part of 'api_client.dart';

/// Today, its layout, modules and house controls.
mixin TodayApi on ApiClientBase {
  // ── Module (welche Bereiche der Server anbietet) ───────────────────────────

  Future<ApiResult<AppModules>> modules() => _cachedGet(
      '/api/modules', 'modules', (j) => AppModules.fromJson(j as Map<String, dynamic>));

  // ── Heute ──────────────────────────────────────────────────────────────────

  Future<ApiResult<TodayData>> today() => _cachedGet(
      '/api/today', 'today', (j) => TodayData.fromJson(j as Map<String, dynamic>));

  // ── Layout von Heute ───────────────────────────────────────────────────────

  Future<ApiResult<TodayLayout>> todayLayout() =>
      _cachedGet('/api/me/today-layout', 'layout:today', TodayLayout.fromJson);

  Future<void> saveTodayLayout(TodayLayout layout) =>
      _send('PUT', '/api/me/today-layout', body: layout.toJson());

  /// Deletes the own layout: the family default (or the built-in one) applies again.
  Future<void> resetTodayLayout() => _send('DELETE', '/api/me/today-layout');

  /// Admin: arrangement every person without an own layout starts from.
  Future<void> saveFamilyTodayLayout(TodayLayout layout) =>
      _send('PUT', '/api/admin/today-layout', body: layout.toJson());

  Future<void> resetFamilyTodayLayout() => _send('DELETE', '/api/admin/today-layout');

  // Steuerfreigaben niemals im ResponseCache speichern oder daraus lesen.
  Future<SourceResult<HouseControl>> houseControls() async {
    try {
      return SourceResult.fromJson(await _send('GET', '/api/house/controls')
        as Map<String, dynamic>, HouseControl.fromJson);
    } on ApiException catch (e) {
      if (e.statusCode == 404) return const SourceResult(status: SourceStatus.notConfigured);
      rethrow;
    }
  }

  /// Schaltet genau einmal. Liefert den von HA bestätigten neuen Zustand, falls HA ihn sofort meldet.
  Future<HouseControl?> houseAction(String entityId, String action, {int? brightness}) async {
    if (houseActionPendingFor(entityId)) throw ApiException(409, l10n.houseActionRunning);
    final epoch = _epoch;
    _houseActionEntities[entityId] = epoch;
    _houseActionFailed = false;
    _houseActionChanges.add(null);
    try {
      final result = await _send('POST', '/api/house/actions', replayOn401: false, body: {
        'entity_id': entityId, 'action': action,
        if (brightness != null) 'brightness': brightness,
      });
      final control = result is Map<String, dynamic> ? result['control'] : null;
      if (control is! Map<String, dynamic>) return null;
      try {
        final confirmed = HouseControl.fromJson(control);
        return confirmed.entityId == entityId ? confirmed : null;
      } catch (_) {
        return null; // unlesbare Bestätigung: App liest den Zustand nach
      }
    } catch (_) {
      // Nur ein sicheres Ergebnisflag, keine privaten Fehlertexte über Remounts.
      if (epoch == _epoch) _houseActionFailed = true;
      rethrow;
    } finally {
      // Alte Sitzungsantworten dürfen eine neuere Aktionssperre nicht lösen.
      if (_houseActionEntities[entityId] == epoch) {
        _houseActionEntities.remove(entityId);
        _houseActionChanges.add(null);
      }
    }
  }
}
