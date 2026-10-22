part of 'api_client.dart';

/// Children's timetable.
mixin TimetableApi on ApiClientBase {
  // ── Timetable of children ──────────────────────────────────────────────────

  Future<List<TimetableChild>> timetableChildren() async =>
      TimetableChild.list(await _send('GET', '/api/timetable/children'));

  Future<TimetableData> timetable(int childId) async => TimetableData.fromJson(
      (await _send('GET', '/api/timetable?child_id=$childId')) as Map<String, dynamic>);

  Future<void> saveTimetableEntry(Map<String, dynamic> body, {int? id}) =>
      id == null ? _send('POST', '/api/timetable', body: body) : _send('PATCH', '/api/timetable/$id', body: body);

  Future<void> deleteTimetableEntry(int id) => _send('DELETE', '/api/timetable/$id');

  /// Returns how many entries were created.
  Future<int> copyTimetableDay(int childId, {required String week, required int from, required List<int> to}) async =>
      (((await _send('POST', '/api/timetable/copy-day',
              body: {'child_id': childId, 'week': week, 'from_weekday': from, 'to_weekdays': to})) as Map)['copied'] as num)
          .toInt();

  Future<int> copyTimetableWeek(int childId, {required String from, required String to}) async =>
      (((await _send('POST', '/api/timetable/copy-week',
              body: {'child_id': childId, 'from_week': from, 'to_week': to})) as Map)['copied'] as num)
          .toInt();

  /// A calendar week (Monday first) with real dates: manual entries merged with the lessons of the child's plugin.
  Future<TimetableWeek> timetableWeek(int childId, DateTime start) async => TimetableWeek.fromJson(
      (await _send('GET', '/api/timetable/week?child_id=$childId&start=${_dateOnly(start)}')) as Map<String, dynamic>);

  Future<TimetableSources> timetableSources() async =>
      TimetableSources.fromJson((await _send('GET', '/api/timetable/sources')) as Map<String, dynamic>);

  /// [sources]: one `{child_id, plugin_id, person_id}` per child; an empty plugin or person removes the mapping.
  Future<TimetableSources> saveTimetableSources(List<Map<String, dynamic>> sources) async => TimetableSources.fromJson(
      (await _send('PUT', '/api/timetable/sources', body: {'sources': sources})) as Map<String, dynamic>);

  /// [abReference]: any day inside an A week (null = no A/B weeks); [holidayFeed]: calendar subscription id.
  Future<void> saveTimetableSettings({DateTime? abReference, String? holidayFeed}) =>
      _send('PUT', '/api/timetable/settings', body: {
        'ab_reference': abReference == null
            ? null
            : '${abReference.year.toString().padLeft(4, '0')}-${abReference.month.toString().padLeft(2, '0')}-${abReference.day.toString().padLeft(2, '0')}',
        'holiday_feed': holidayFeed,
      });
}
